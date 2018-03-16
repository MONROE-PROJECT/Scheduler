#!/bin/bash
set -e
SCHEDID=$1

echo "VM: Starting deployment"

BASEDIR=/experiments/user
STATUSDIR=$BASEDIR
mkdir -p $BASEDIR

VM_PADDING="300" # MB, neded for preparing initramfs among others. 

ERROR_IMAGE_NOT_FOUND=12
ERROR_INSUFFICIENT_DISK_SPACE=101

if [ -f $BASEDIR/$SCHEDID.conf ]; then
  CONFIG=$(cat $BASEDIR/$1.conf);
  IS_INTERNAL=$(echo $CONFIG | jq -r '.internal // empty');
  BDEXT=$(echo $CONFIG | jq -r '.basedir // empty');
  VM_OS_DISK=$(echo $CONFIG | jq -r '.vm_os_disk // empty');
fi
if [ ! -z "$IS_INTERNAL" ]; then
  BASEDIR=/experiments/monroe${BDEXT}
fi
mkdir -p $BASEDIR

if [[ ! -z "$VM_OS_DISK" && -f "$VM_OS_DISK" ]]; then
    logger -t "VM: Using already converted os disk in $VM_OS_DISK"
    exit 0
fi

EXISTED=$(docker images -q monroe-$SCHEDID)
if [ -z "$EXISTED" ]; then
    logger -t "VM: Deployment failed due to missing image: monroe-$SCHEDID"
    exit $ERROR_IMAGE_NOT_FOUND;
fi


echo "VM: Start Conversion of container : monroe-$SCHEDID"
IMAGE_SIZE=$(docker images --format "{{.Size}}"  monroe-$SCHEDID | grep MB | tr -dc '0-9.' |cut -f1 -d',') # Assumes MB as GB/TB is way too big and KB is too small
echo "Docker image is ${IMAGE_SIZE}Mb, adding ${VM_PADDING}Mb"
echo -n " Checking for disk space: "
IMAGE_SIZE=$(docker images --format "{{.Size}}"  monroe-$SCHEDID | grep MB | tr -dc '0-9.' |cut -f1 -d',') # Assumes MB as GB/TB is way too big and KB is too small
VM_PADDED_SIZE=$(( $IMAGE_SIZE + $VM_PADDING ))  
DISKSPACE=$(df /var/lib/docker --output=avail|tail -n1)
if [[ -z "$IMAGE_SIZE" || "$DISKSPACE" -lt $(( 100000 + ( $VM_PADDED_SIZE ) * 1024 )) ]]; then
    logger -t "Insufficient disk space for vm conversion reported: $DISKSPACE"
    exit $ERROR_INSUFFICIENT_DISK_SPACE;
fi
echo "ok."

# Start the conversion
VM_OS_DIR=$BASEDIR/$SCHEDID.os
mkdir -p ${VM_OS_DIR}
VM_OS_DISK="${VM_OS_DIR}/image.qcow2"

RAMDISK_MP=$BASEDIR/$SCHEDID.tmp
mkdir -p $RAMDISK_MP
TMP_VM_FILE=$RAMDISK_MP/tar_dump


mountpoint -q $RAMDISK_MP || {
    echo "VM: Creating $VM_PADDED_SIZE Mb ramdisk in $RAMDISK_MP"
    mount -t tmpfs -o size=${VM_PADDED_SIZE}m tmpfs $RAMDISK_MP
}

echo "VM: Exporting image content to a tar archive"
#doable but slowert due to compression
#docker export ${container_id}  | gzip > ${ram_disk_path}/${filesystem_image}.gz
VM_CID=$(docker run -d --net=none  monroe-$SCHEDID ls)
docker export $VM_CID > $TMP_VM_FILE
docker rm -f $VM_CID || true
docker rmi monroe-$SCHEDID || true

echo -n "VM: Creating and mounting ${VM_OS_DIR}"
yes|lvcreate -L${VM_PADDED_SIZE} -nvirtualization-${SCHEDID} vg-monroe
yes|mkfs.ext4 /dev/vg-monroe/virtualization-${SCHEDID}
yes|mount /dev/vg-monroe/virtualization-${SCHEDID} ${VM_OS_DIR}

echo -n "VM: Creating new QCOW2 disk image"
virt-make-fs \
    --size=${VM_PADDED_SIZE}M \
    --format=qcow2 \
    --type=ext4 \
    --partition -- ${TMP_VM_FILE} ${VM_OS_DISK}

echo "VM: Unmounting ramdisk"
rm -f ${TMP_VM_FILE}
umount ${RAMDISK_MP}
#sleep 3
#rm -rf ${RAMDISK_MP}
CONFIG=$(echo $CONFIG | jq '.vm_os_disk="'$VM_OS_DISK'"')
echo $CONFIG > $BASEDIR/$SCHEDID.conf