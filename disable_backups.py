#!/usr/bin/env python
# 
# This script will disable cpanel backups for customer which have plan named like Unlimited*
# 
# Add this in crontab
# 0 0 * * 0 /root/disable_backups.py --toggle-backups
# 
# 0 0 * * 0 /root/disable_backups.py --toggle-backups
#

import yaml
import argparse
import subprocess
import os
import sys
import json
import re

diff_in_megs = 500			# difference to trigger warning if disk usage differ with x megabytes
diff_in_inodes = 5000		# difference to trigger warning if inode usage differ with x inodes
overquota_allow = 2000		# amount of inodes to increase for over quota
overquota_inodes = 300000	# do not increase inodes for customers who overquota this limit
diskquotalimit_backup = 30000 # 30G limit for backup to work
warninglimit_inodes = 150000
planlist_file = 'plan_list.yaml'

parser = argparse.ArgumentParser()
parser.add_argument('-b', '--toggle-backups', nargs='?', default=0)
parser.add_argument('-d', '--check-diskusage-limit', nargs='?', default=0)
parser.add_argument('-i', '--check-inodeusage-limit', nargs='?', default=0)
parser.add_argument('-p', '--apply-package-limits', nargs='?', default=0)
parser.add_argument('-q', '--apply-quota-limits', nargs='?', default=0)
parser.add_argument('-fi', '--fix-inode-limits', nargs='?', default=0, help="Check if inodelimit on account match with inodelimit on package, require --check-inodeusage-limit")
parser.add_argument('-oq', '--fix-overquota', nargs='?', default=0, help="Increase inode quota limit with some amount, to allow hosting to work, require --check-inodeusage-limit")
args = parser.parse_args()

print args

backup_messages=[];
diskusage_messages=[];
inodeusage_messages=[];
overquota_messages=[];
apply_packagelimit_messages='';
apply_inodelimit_messages='';

###########################
# run code
###########################

def toggle_backups(user, state):
	p = subprocess.Popen(['/usr/local/cpanel/bin/whmapi1', 'toggle_user_backup_state', 'user='+user, 'legacy=0', '--output=json'], stdout=subprocess.PIPE)
	out, err = p.communicate()
	result = json.loads(out).get('data').get('toggle_status')
	if result != state:
		toggle_backups(user, state)
	
def should_ignore(user):
	try:
		if excluded_users[user] == 'ignore':
			print("[INFO] Should enable backup for "+user+" due exclude_users.txt file");
			toggle_backups(user, 1)
			return True
	
	except:
		return False

def get_plan_by_name(plan):
	found=False
	default_plan=False
	for j in plans:
		if j.get('name') == 'default':
			default_plan = j
			continue
			
		if j.get('name') == plan:
			found=True
			plan2 = j
			
		if re.match("^Unlimited_One", j.get('name')) and re.match("^Unlimited_One", plan):
			found=True
			plan2 = j
			
		if re.match("^Unlimited_Plus", j.get('name')) and re.match("^Unlimited_Plus", plan):
			found=True
			plan2 = j
			
		if re.match("^Unlimited_Full", j.get('name')) and re.match("^Unlimited_Full", plan):
			found=True
			plan2 = j
	
	if found==True:
		plan2['inodelimit'] = plan2.get('inodelimit') if plan2.get('inodelimit') != None else default_plan.get('inodelimit')
		plan2['backup'] = plan2.get('backup') if plan2.get('backup') != None else default_plan.get('backup')
		return plan2
	else:
		return default_plan
	
###########################
# run code
###########################

p = subprocess.Popen(['/usr/local/cpanel/bin/whmapi1', 'listaccts', 'want=user,backup,plan,diskused,inodesused,inodeslimit'], stdout=subprocess.PIPE)
out, err = p.communicate()
users = yaml.load(out).get('data').get('acct')
current_state = users
current_state_users = {}

if os.path.isfile(planlist_file): 
	fh = open(planlist_file, "r")
	plans = yaml.safe_load(fh).get('plans')
	fh.close()

if args.toggle_backups != 0:
	# load exceptions
	excluded_users={}
	try:
		f = open('exclude_users.txt', 'r')
		c = f.readlines()
		f.close()
		for i in c:
			i = i.strip()
			excluded_users[i] = 'ignore'
	except:
		print("[WARNING] missing exclude_users.txt file, ignoring\n")
		
	print "[INFO] Following exception found:", excluded_users.keys()


for i in users:
	user = i.get('user')
	backup = i.get('backup')
	plan = i.get('plan')
	diskused = int(i.get('diskused').replace('M', ''))
	backup_storage=10000
	current_state_users[user]=i
	
	if args.toggle_backups == 0 or should_ignore(user) == True:
		continue
	
	if diskused > diskquotalimit_backup:
		backup_messages.append("Disable backups for "+user+" due to high disk usage "+str(diskused))
		toggle_backups(user, 0)
		continue
	
	should_do_backup = get_plan_by_name(i.get('plan')).get('backup')
	if should_do_backup == None:
		print "[WARNING] I can't find if i should enable or disable backups for plan", i.get('plan')
		should_do_backup = 1
	
	if should_do_backup != i.get('backup'):
		if should_do_backup == 1:
			backup_messages.append("We should do backups for "+user+" so i enable backups")
		else:
			backup_messages.append("We should not do backups for "+user+" so i disable backups")
		
		toggle_backups(user, should_do_backup)
	
#############################################################
# calculate difference between disk usage from last run
# 
# load old disk usage state
old_state_file = '/tmp/disk_usage.state'
if os.path.isfile(old_state_file):
	fh = open(old_state_file, "r")
	old_state = yaml.safe_load( fh )
	fh.close()
	for i in old_state:
		user = i.get('user')
		
		try:
			if current_state_users.get(user).get('inodesused') == None:
				print "[INFO] Processing", user
		except:
			print "[WARNING] Skip user", user, "due inexistence"
			continue;
		
		diff_du = int(current_state_users.get(user).get('diskused').replace('M', '')) - int(i.get('diskused').replace('M', ''))
		if diff_du >= diff_in_megs:
			diskusage_messages.append("Difference between last week and this for disk usage of user "+user+" is "+str(diff_du)+"MB")
		
		diff_inode = int(current_state_users.get(user).get('inodesused')) - int(i.get('inodesused'))
		if diff_inode >= diff_in_inodes:
			inodeusage_messages.append("Difference between last week and this for disk usage of user "+user+" is "+str(diff_inode)+" inodes")
		
		if args.check_diskusage_limit != 0 and int(current_state_users.get(user).get('diskused').replace('M', '')) > 70000:
			diskusage_messages.append("High disk usage for user "+user+", "+current_state_users.get(user).get('diskused')+", package: "+i.get('plan'))
		
		if args.check_inodeusage_limit != 0 and current_state_users.get(user).get('inodesused') > warninglimit_inodes:
			inodeusage_messages.append("High inode usage for user "+user+", "+str(current_state_users.get(user).get('inodesused'))+"/"+str(i.get('inodeslimit'))+" inodes, package: "+i.get('plan'))
		
		if args.check_inodeusage_limit != 0:
			if current_state_users.get(user).get('inodeslimit') == 'unlimited':
				print "[WARNING] Account with unlimited inodes", user, ":",str(current_state_users.get(user).get('inodesused')),"/", i.get('inodeslimit'), "inodes, package", i.get('plan')
			if args.fix_inode_limits != 0:
				values = {
					"user": user,
					"inodelimit": get_plan_by_name(current_state_users.get(user).get('plan')).get('inodelimit')
				}
				if current_state_users.get(user).get('inodeslimit') == 'unlimited' or int(values.get('inodelimit')) != int(current_state_users.get(user).get('inodeslimit')): # package vs user quota
					cmd = "cl-quota -u %(user)s -S %(inodelimit)d -H %(inodelimit)d" % values
					print "[VERBOSE] Executing", cmd
					
					ret = subprocess.call(cmd, shell=True)
					if ret != 0:
						print "[ERROR] Error while executing" ,cmd
			else:
				if current_state_users.get(user).get('inodeslimit') != 'unlimited':
					overquota_inodes = int(current_state_users.get(user).get('inodesused')) - int(current_state_users.get(user).get('inodeslimit'))
					
					if overquota_inodes > 500:
						overquota_messages.append("Over quota inodes for user "+user+", "+str(current_state_users.get(user).get('inodesused'))+"/"+ current_state_users.get(user).get('inodeslimit')+" inodes, package: "+current_state_users.get(user).get('plan'))
					
					if args.fix_overquota != 0 and overquota_inodes > 2:
						newinodelimit = int(current_state_users.get(user).get('inodesused')) + overquota_allow
						values = {"user": user, "inodelimit": newinodelimit}
						overquota_messages.append("Fixing overquota for "+user+" new limit is "+str(newinodelimit)+" normal limit should be "+ str(current_state_users.get(user).get('inodeslimit')))
						cmd = "cl-quota -u %(user)s -S %(inodelimit)d -H %(inodelimit)d" % values
						print "[VERBOSE] Executing", cmd
						
						ret = subprocess.call(cmd, shell=True)
						if ret != 0:
							print "[ERROR] Error while executing" ,cmd

# update old_state_file
fh = open(old_state_file, "w")
yaml.safe_dump( current_state, fh , explicit_start=True)
fh.close()

# check packages resources which are met or not
if args.apply_package_limits != 0 or args.apply_quota_limits != 0:
	for j in plans:
		if j.get('name') == 'default':
			default_plan = j
	
	p = subprocess.Popen(['lvectl', 'package-list', '--json'], stdout=subprocess.PIPE)
	out, err = p.communicate()
	lvectl_pkglist = json.loads(out).get('data')
	for i in lvectl_pkglist:
		name = i.get('ID')
		f = default_plan
		iii = 0
		
		# find appropriate parameters
		for j in plans:
			if name == j.get('name'):
				iii = 1
				f = j
			if re.match("^Unlimited_One", j.get('name')) and re.match("^Unlimited_One", name):
				iii = 1
				f = j
			if re.match("^Unlimited_Plus", j.get('name')) and re.match("^Unlimited_Plus", name):
				iii = 1
				f = j
			if re.match("^Unlimited_Full", j.get('name')) and re.match("^Unlimited_Full", name):
				iii = 1
				f = j
		
		if iii == 0:
			print "Use default plan for ",name , default_plan
		
		values = {}
		values['name'] = name
		values['cpu'] = f.get('cpu') if f.get('cpu') != None else default_plan.get('cpu')
		values['io'] = f.get('io') if f.get('io') != None else default_plan.get('io')
		values['iops'] = f.get('iops') if f.get('iops') != None else default_plan.get('iops')
		values['nproc'] = f.get('nproc') if f.get('nproc') != None else default_plan.get('nproc')
		values['memory'] = f.get('memory') if f.get('memory') != None else default_plan.get('memory')
		values['ep'] = f.get('ep') if f.get('ep') != None else default_plan.get('ep')
		values['io'] = values['io']*1024
		values['inodelimit'] = f.get('inodelimit') if f.get('inodelimit') != None else default_plan.get('inodelimit')
		
		# change package params
		if args.apply_package_limits != 0:
			cmd = "lvectl package-set '%(name)s' --speed=%(cpu)d%% --io=%(io)d --iops=%(iops)d --nproc=%(nproc)d --vmem=%(memory)dM --pmem=%(memory)dM --maxEntryProcs=%(ep)d" % values
			print "Executing", cmd
			
			ret = subprocess.call(cmd, shell=True)
			if ret != 0:
				print "Error while executing" ,cmd
			
		if args.apply_quota_limits != 0:
			cmd = "cl-quota -p '%(name)s' -S %(inodelimit)d -H %(inodelimit)d" % values
			print "Executing", cmd
			
			ret = subprocess.call(cmd, shell=True)
			if ret != 0:
				print "Error while executing" ,cmd


if args.toggle_backups != 0:
	print "\nList of accounts with switched backup feature:\n"
	for i in backup_messages:
		print i

if args.check_diskusage_limit != 0:
	print "\nList of accounts with disk usage issues:\n"
	for i in diskusage_messages:
		print i

if args.check_inodeusage_limit != 0:
	print "\nList of accounts with inode usage issues:\n"
	for i in inodeusage_messages:
		print i

if args.check_inodeusage_limit != 0 and args.fix_inode_limits == 0:
	print "\nList of accounts with overquota issues:\n"
	for i in overquota_messages:
		print i
