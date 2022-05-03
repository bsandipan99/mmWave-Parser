#!/bin/bash
cd /home/arghasen10/Documents/github/AWR1642-Read-Data-Python-MMWAVE-SDK-2/dataset
count=$(ls | wc -l)
echo "$count"
count=$((count-1))
echo $count
lsdir=$(ls -lt | tail -n $count)
SUB='.csv'
for file in $lsdir
do
	if [[ "$file" == *"$SUB"* ]]; then
		echo "$file transfer started";
		scp "$file" argha@10.5.20.130:/mnt/3/althome/argha/dataset;
		sleep 2;
		rm "$file";
		echo "$file deleted";
	fi
done

