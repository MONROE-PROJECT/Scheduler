#!/bin/bash
set -e

SCHEDID=$1
STATUS=$2
CONTAINER=monroe-$SCHEDID

VM_PADDDING="300" # MB

BASEDIR=/experiments/user
STATUSDIR=$BASEDIR
mkdir -p $BASEDIR

if [ -f $BASEDIR/$SCHEDID.conf ]; then
  CONFIG=$(cat $BASEDIR/$SCHEDID.conf);
  IS_INTERNAL=$(echo $CONFIG | jq -r '.internal // empty');
  IS_SSH=$(echo $CONFIG | jq -r '.ssh // empty');
  IS_VM=$(echo $CONFIG | jq -r '.vm // empty');
  BDEXT=$(echo $CONFIG | jq -r '.basedir // empty');
  EDUROAM_IDENTITY=$(echo $CONFIG | jq -r '._eduroam.identity // empty');
  EDUROAM_HASH=$(echo $CONFIG | jq -r '._eduroam.hash // empty');
fi
if [ ! -z "$IS_INTERNAL" ]; then
  BASEDIR=/experiments/monroe${BDEXT}
  mkdir -p $BASEDIR
  echo $CONFIG > $BASEDIR/$SCHEDID.conf
  # redirect output to log file
  exec > $BASEDIR/start.log 2>&1
else
  exec >> $BASEDIR/$SCHEDID/start.log 2>&1
fi

NOERROR_CONTAINER_IS_RUNNING=0

ERROR_CONTAINER_DID_NOT_START=10
ERROR_NETWORK_CONTEXT_NOT_FOUND=11
ERROR_IMAGE_NOT_FOUND=12
ERROR_MAINTENANCE_MODE=13

echo -n "Checking for maintenance mode... "
MAINTENANCE=$(cat /monroe/maintenance/enabled || echo 0)
if [ $MAINTENANCE -eq 1 ]; then
   echo 'failed; node is in maintenance mode.' > $STATUSDIR/$SCHEDID.status
   echo "enabled."
   exit $ERROR_MAINTENANCE_MODE;
fi
echo "disabled."

echo -n "Ensure network and containers are set up... "
mkdir -p /var/run/netns

# Container boot counter and measurement UID

COUNT=$(cat $BASEDIR/${SCHEDID}.counter 2>/dev/null || echo 0)
COUNT=$(($COUNT + 1))
echo $COUNT > $BASEDIR/${SCHEDID}.counter

NODEID=$(</etc/nodeid)
IMAGEID=$(docker images -q --no-trunc monroe-$SCHEDID)

if [ -z "$IMAGEID" ]; then
    echo "experiment container not found."
    exit $ERROR_IMAGE_NOT_FOUND;
fi

GUID="${IMAGEID}.${SCHEDID}.${NODEID}.${COUNT}"

# replace guid in the configuration

CONFIG=$(echo $CONFIG | jq '.guid="'$GUID'"|.nodeid="'$NODEID'"')
echo $CONFIG > $BASEDIR/$SCHEDID.conf
echo "ok."

# setup eduroam if available

if [ ! -z "$EDUROAM_IDENTITY" ]; then
    /usr/bin/eduroam-login.sh $EDUROAM_IDENTITY $EDUROAM_HASH &
fi

# Check if we have space for conversion

if [ ! -z "$IS_VM" ]; then
    echo -n "VM: Checking for disk space... "
    IMAGE_SIZE=$(docker images --format "{{.Size}}" $CONTAINER | grep MB | tr -dc '0-9.' | tr '.' ',') # Assumes MB as GB/TB is way too big and KB is too small
    DISKSPACE=$(df /var/lib/docker --output=avail|tail -n1)
    if [[ -z "$IMAGE_SIZE" || "$DISKSPACE" -lt $(( 100000 + ( $IMAGE_SIZE + $VM_PADDING) * 1024 )) ]]; then
        logger -t "container-start Insufficient disk space for vm conversion reported: $DISKSPACE";
        exit $ERROR_INSUFFICIENT_DISK_SPACE;
    fi

    # Start the conversion
    echo -n "VM: Image is ${IMAGE_SIZE}Mb, adding ${VM_PADDING}Mb"
    VM_PADDED_SIZE=$(( IMAGE_SIZE + VM_PADDING ))

    RAMDISK_MP=/tmp/tmpvmramdisk
    mkdir -p $RAMDISK_MP
    TMP_VM_FILE=$RAMDISK_MP/$SCHEDID

    echo -n "VM: Creating $VM_PADDED_SIZE Mb ramdisk in $RAMDISK_MP"
    mount -t tmpfs -o size=${VM_PADDED_SIZE}m tmpfs $RAMDISK_MP

    echo -n "VM: Exporting image content to a tar archive"
    #doable but slowert due to compression
    #docker export ${container_id}  | gzip > ${ram_disk_path}/${filesystem_image}.gz
    VM_CID=$(docker run -d --net=none $CONTAINER ls)
    docker export $VM_CID > $TMP_VM_FILE

    VM_OS_DIR=/tmp/${SCHEDID}.OS
    mkdir -p ${VM_OS_DIR}

    echo -n "VM: Creating and mounting ${VM_OS_DIR}"
    yes|lvcreate -L${VM_PADDED_SIZE} -nvirtualization-${SCHEDID} vg-monroe
    yes|mkfs.ext4 /dev/vg-monroe/virtualization-${SCHEDID}
    yes|mount /dev/vg-monroe/virtualization-${SCHEDID} ${VM_OS_DIR}

    VM_OS_DISK="${VM_OS_DIR}/image.qcow2"
    echo -n "VM: Creating new QCOW2 disk image"
    virt-make-fs \
      --size=${VM_PADDED_SIZE}M \
      --format=qcow2 \
      --type=ext4 \
      --partition -- ${TMP_VM_FILE} ${VM_OS_DISK}

    echo "VM: Unmounting ramdisk"
    rm -f ${TMP_VM_FILE}
    umount ${RAMDISK_MP}
    sleep 3
    rm -rf ${RAMDISK_MP}
fi
### START THE CONTAINER ###############################################

echo -n "Starting container... "
if [ -d $BASEDIR/$SCHEDID ]; then
    MOUNT_DISK="-v $BASEDIR/$SCHEDID:/monroe/results -v $BASEDIR/$SCHEDID:/outdir"
fi
if [ -d /experiments/monroe/tstat ]; then
    TSTAT_DISK="-v /experiments/monroe/tstat:/monroe/tstat:ro"
fi

# check that this container is not running yet
if [ ! -z "$(docker ps | grep monroe-$SCHEDID)" ]; then
    echo "already running."
    exit $NOERROR_CONTAINER_IS_RUNNING;
fi

# identify the monroe/noop container, running in the
# network namespace called 'monroe'
MONROE_NAMESPACE=$(docker ps --no-trunc -aqf name=monroe-namespace)
if [ -z "$MONROE_NAMESPACE" ]; then
    echo "network context missing."
    exit $ERROR_NETWORK_CONTEXT_NOT_FOUND;
fi

if [ ! -z "$IS_SSH" ]; then
    OVERRIDE_ENTRYPOINT=" --entrypoint=dumb-init "
    OVERRIDE_PARAMETERS=" /bin/bash /usr/bin/monroe-sshtunnel-client.sh "
fi

cp /etc/resolv.conf $BASEDIR/$SCHEDID/resolv.conf.tmp

# drop all network traffic for 30 seconds (idle period)
nohup /bin/bash -c 'sleep 35; circle start' &
iptables -F
iptables -P INPUT DROP
iptables -P OUTPUT DROP
iptables -P FORWARD DROP
sleep 30
circle start

if [ ! -z "$IS_VM" ]; then
    mkdir -p $BASEDIR/$SCHEDID-conf
    cp $BASEDIR/$SCHEDID/resolv.conf.tmp $BASEDIR/$SCHEDID-conf/resolv.conf
    cp $BASEDIR/$SCHEDID.conf $BASEDIR/$SCHEDID-conf/config
    cp  /etc/nodeid $BASEDIR/$SCHEDID-conf/nodeid
    cp /tmp/dnsmasq-servers-netns-monroe.conf $BASEDIR/$SCHEDID-conf/dns
    ./vm-start.sh $SCHEDID \
                  $STATUS \
                  ${VM_OS_DISK} \
                  $BASEDIR/$SCHEDID \
                  $BASEDIR/$SCHEDID-conf \
                  $OVERRIDE_ENTRYPOINT \
                  $OVERRIDE_PARAMETERS &
else
        CID_ON_START=$(docker run -d $OVERRIDE_ENTRYPOINT  \
           --name=monroe-$SCHEDID \
           --net=container:$MONROE_NAMESPACE \
           --cap-add NET_ADMIN \
           --cap-add NET_RAW \
           -v $BASEDIR/$SCHEDID/resolv.conf.tmp:/etc/resolv.conf \
           -v $BASEDIR/$SCHEDID.conf:/monroe/config:ro \
           -v /etc/nodeid:/nodeid:ro \
           -v /tmp/dnsmasq-servers-netns-monroe.conf:/dns:ro \
           $MOUNT_DISK \
           $TSTAT_DISK \
           $CONTAINER $OVERRIDE_PARAMETERS)
fi
echo "ok."

# start accounting
echo "Starting accounting."
/usr/bin/usage-defaults 2>/dev/null || true

if [ -z "$IS_VM" ]; then
    # CID: the runtime container ID
    CID=$(docker ps --no-trunc | grep $CONTAINER | awk '{print $1}' | head -n 1)

    if [ -z "$CID" ]; then
        echo 'failed; container exited immediately' > $STATUSDIR/$SCHEDID.status
        echo "Container exited immediately."
        echo "Log output:"
        docker logs -t $CID_ON_START || true
        echo ""
        exit $ERROR_CONTAINER_DID_NOT_START;
    fi

    # PID: the container process ID
    PID=$(docker inspect -f '{{.State.Pid}}' $CID)

    if [ ! -z $PID ]; then
      echo "Started docker process $CID $PID."
    else
      echo 'failed; container exited immediately' > $STATUSDIR/$SCHEDID.status
      echo "Container exited immediately."
      echo "Log output:"
      docker logs -t $CID_ON_START || true
      exit $ERROR_CONTAINER_DID_NOT_START;
    fi

    echo $PID > $BASEDIR/$SCHEDID.pid
    if [ -z "$STATUS" ]; then
      echo 'started' > $STATUSDIR/$SCHEDID.status
    else
      echo $STATUS > $STATUSDIR/$SCHEDID.status
    fi
fi
sysevent -t Scheduling.Task.Started -k id -v $SCHEDID
echo "Startup finished $(date)."
