#!/bin/bash

#check existence of rclone, if not then download
#https://stackoverflow.com/questions/592620/how-can-i-check-if-a-program-exists-from-a-bash-script
if ! command -v rclone &> /dev/null
then
    echo "rclone could not be found,please download"
    exit
fi




# these configuration are necessary and can be found in https://rclone.org/drive/
# Strongly recommend to use your own clientid to speedup your transmit
gdrive_client_secret="insert_here"
gdrive_client_id="insert_here"
gdrive_root_folder_id="insert_here"

#a random name for the rclone config, can be any string you want
remote_config_name="shared_drive"


#insert the path of the local folder  you want to sync with Google Drive 
local_sync_path="your_folder_on_local"
#insert the path of the remote folder on Google Drive you want to sync 
remote_sync_path="your_folder_on_remote"




# Guide to optimizing rclone is here:
#https://forum.rclone.org/t/how-drive-upload-cutoff-and-drive-chunk-size-works/1430
#https://forum.rclone.org/t/strageties-for-speeding-up-rclone-sync-times/20588/3
#https://forum.rclone.org/t/how-to-speed-up-google-drive-sync/8444

#Above the upload cutoff rclone will use a multi-part upload which is less efficient that uploading it directly, but better for uploading big files. 
# Why is it better?
rclone config create $remote_config_name drive  \
    client_id=$gdrive_client_id \
    client_secret=$gdrive_client_secret \
    root_folder_id=$gdrive_root_folder_id \
    scope=drive \
    auth_url=https://accounts.google.com/o/oauth2/auth \
    token_url=https://oauth2.googleapis.com/token \
    upload_cutoff=4Mi \
    chunk_size=32Mi \
    pacer_min_sleep=8ms \
    pacer_burst=1000 




#for impersonation another user when using a service account. Hmmm this doesn't sound right. Maybe rclone got it wrong
# https://cloud.google.com/iam/docs/understanding-service-accounts#:~:text=A%20service%20account%20is%20a,on%20virtual%20machines%20(VMs).




# Sync the 2 folder for the first time, best not to touch this again
rclone bisync $remote_config_name:$remote_sync_path $local_sync_path --transfers=40 --checkers=80 --tpslimit=300 --tpslimit-burst 100 --max-backlog 200000   --fast-list  -v -v  --resync


cp gdrive_sync_template.service gdrive_sync.service
SERVICE_LOCATION="$(pwd)"
# this bash substitution method only works on bash, not zsh
sed -i -r " s#<this_project_location>#${SERVICE_LOCATION//#/\\#}#; \
            s#<remote_rclone_config_name>#$remote_config_name#; \
            s#<remote_sync_path>#${remote_sync_path//#/\\#}#; \
            s#<local_sync_path>#${local_sync_path//#/\\#}#; " gdrive_sync.service



sudo cp gdrive_sync.service /etc/systemd/system/ && sudo systemctl daemon-reload
sudo systemctl enable --now gdrive_sync.service
