#!/bin/bash
set -e
SCHEDID=$1

echo "vm-deploy: Starting deployment"

BASEDIR=/experiments/user
STATUSDIR=$BASEDIR
mkdir -p $BASEDIR

VM_PADDING="300" # MB neded for preparing initramfs among others. 

ERROR_IMAGE_NOT_FOUND=12
ERROR_INSUFFICIENT_DISK_SPACE=101

if [ -f $BASEDIR/$SCHEDID.conf ]; then
  CONFIG=$(cat $BASEDIR/$1.conf);
  IS_INTERNAL=$(echo $CONFIG | jq -r '.internal // empty');
  BDEXT=$(echo $CONFIG | jq -r '.basedir // empty');
fi
if [ ! -z "$IS_INTERNAL" ]; then
  BASEDIR=/experiments/monroe${BDEXT}
fi
mkdir -p $BASEDIR

VM_OS_MNT=$BASEDIR/$SCHEDID.os
VM_OS_DISK=${VM_OS_MNT}/image.qcow2

if [[ -f "$VM_OS_DISK" ]]; then
    #logger -t "VM" "Using already converted os disk in $VM_OS_DISK"
    echo "vm-deploy: Using already converted os disk in $VM_OS_DISK"
    exit 0
fi

EXISTED=$(docker images -q monroe-$SCHEDID)
if [ -z "$EXISTED" ]; then
    #logger -t "VM" "Deployment failed due to missing image: monroe-$SCHEDID"
    echo "vm-deploy: Deployment failed due to missing image: monroe-$SCHEDID"
    exit $ERROR_IMAGE_NOT_FOUND;
fi


echo "vm-deploy: Start Conversion of container monroe-$SCHEDID"
IMAGE_SIZE=$(docker images --format "{{.Size}}"  monroe-$SCHEDID | grep MB | tr -dc '0-9.' | cut -f1 -d'.') # Assumes MB as GB/TB is way too big and KB is too small
echo -n "vm-deploy: Docker image is ${IMAGE_SIZE}Mb, adding ${VM_PADDING}Mb, checking for disk space... "
VM_PADDED_SIZE=$(( $IMAGE_SIZE + $VM_PADDING ))  
# Black magic 
DISKSPACE=$(df /var/lib/docker --output=avail|tail -n1)
if [[ -z "$IMAGE_SIZE" || "$DISKSPACE" -lt $(( 100000 + ( $VM_PADDED_SIZE ) * 1024 )) ]]; then
    #logger -t "VM" "Insufficient disk space for vm conversion reported: $DISKSPACE"
    echo "vm-deploy: Insufficient disk space for vm conversion reported: $DISKSPACE"
    exit $ERROR_INSUFFICIENT_DISK_SPACE;
fi
echo "ok."

# Start the conversion
VM_TMP_MNT=$BASEDIR/$SCHEDID.rd
mkdir -p $VM_TMP_MNT
TMP_VM_FILE=$VM_TMP_MNT/tar_dump


mountpoint -q $VM_TMP_MNT || {
    echo -n "vm-deploy: Creating $VM_PADDED_SIZE Mb ramdisk in $VM_TMP_MNT... "
    mount -t tmpfs -o size=${VM_PADDED_SIZE}m tmpfs $VM_TMP_MNT
    echo "ok." 
}

echo -n "vm-deploy: Exporting image content to a tar archive... "
#doable but slowert due to compression
#docker export ${container_id}  | gzip > ${ram_disk_path}/${filesystem_image}.gz
VM_CID=$(docker run -d --net=none  monroe-$SCHEDID ls)
(docker export $VM_CID > ${TMP_VM_FILE})
docker rm -f $VM_CID &> /dev/null || true
docker rmi monroe-$SCHEDID &> /dev/null || true
echo "ok." 

echo  -n "vm-deploy: Creating and mounting ${VM_OS_MNT}... "
#More black magic
yes|lvremove -f /dev/vg-monroe/virtualization-${SCHEDID} &> /dev/null || true
yes|lvcreate -L${VM_PADDED_SIZE} -nvirtualization-${SCHEDID} vg-monroe
yes|mkfs.ext4 -q /dev/vg-monroe/virtualization-${SCHEDID}
mkdir -p ${VM_OS_MNT}
yes|umount -f ${VM_OS_MNT} &> /dev/null || true
yes|mount /dev/vg-monroe/virtualization-${SCHEDID} ${VM_OS_MNT}
echo "ok."
echo -n "vm-deploy: Creating new QCOW2 disk image... "
virt-make-fs \
    --size=${VM_PADDED_SIZE}M \
    --format=qcow2 \
    --type=ext4 \
    --partition -- ${TMP_VM_FILE} ${VM_OS_DISK}
echo "ok."

echo -n "vm-deploy: Unmounting ramdisk... "
umount -f ${VM_TMP_MNT}
echo "ok."
