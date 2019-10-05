#!/usr/bin/env python

import yaml
import os
import json
import requests

secret_file = 'secret.yaml'

if os.path.isfile(secret_file): 
	fh = open(secret_file, "r")
	whmcs_servers = yaml.safe_load(fh).get('whmcs')
	fh.close()

backup_addons = [
	'100GB Backup (billed annually)',
	'Business 250 Backup',
	'Business 500 backup',
	'Backup for Unlimited Hosting',
	'Daily backup'
]

result_file = open('updated.txt', 'w')

for i in whmcs_servers:
	uri = 'https://'+i.get('url')+'/includes/api.php'
	payload = {'action': 'GetClientsAddons',
		'username': i.get('username'),
		'password': i.get('password'),
		'responsetype': 'json'
	}
	
	r = requests.post(uri, data=payload)
	try:
		response = r.json()
	except:
		print("Unexpected response after GetClientsAddons request")
		print(r.text)
		continue
	
	for j in r.json().get('addons').get('addon'):
		for k in backup_addons:
			if k == j.get('name') and (j.get('status') == 'Active' or j.get('status') == 'Suspended'):
				#print(j)
				serviceid = j.get('serviceid')
				
				payload = {'action': 'GetClientsProducts',
					'serviceid': serviceid,
					'username': i.get('username'),
					'password': i.get('password'),
					'responsetype': 'json'}
				
				r = requests.post(uri, data=payload)
				response = r.json()
				#print(response)
				for l in r.json().get('products').get('product'):
					print('Found product '+l.get('domain')+' with '+j.get('name')+"  ("+j.get('status')+")")
					result_file.write(l.get('username')+"\n")
					
result_file.close()
