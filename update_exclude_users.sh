#!/bin/bash

SERVERS="web1 web2 web3"

cp updated.txt exclude_users.txt
for i in $SERVERS; do
	scp exclude_users.txt $i:/root/disable_backups
done
