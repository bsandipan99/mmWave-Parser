#!/bin/bash
cd /home/arghasen10/Documents/github/AWR1642-Read-Data-Python-MMWAVE-SDK-2/videodata
count=$(ls | wc -l)
echo "$count"
count=$((count-1))
echo $count
lsdir=$(ls -lt | tail -n $count)
SUB='.avi'
for file in $lsdir ;
 do
	 if [[ "$file" == *"$SUB"* ]]; then
	 echo "$file transfer started";
	 scp "$file" argha@10.5.20.130:/mnt/3/althome/argha/videodata;
	 rm "$file";
	 echo "$file deleted";
	 fi;
 done

