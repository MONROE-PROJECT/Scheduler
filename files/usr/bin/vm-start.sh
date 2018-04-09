#!/bin/bash
set -e

SCHEDID=$1
STATUS=$2
VM_OS_DISK=$3
CONF_DIR=$4
MOUNT_DISK=$5
OVERRIDE_ENTRYPOINT=$6
OVERRIDE_PARAMETERS=$7

MNS=???

disk_imae=$VM_OS_DISK

VTAPPREFIX=macvtap

if [ ! -f "${disk_image}" ]; then
        echo "Missing disk image (${disk_image}), exiting"
        exit 1
fi
# Enumerate the interfaces and:
# 1. Create the vtap interfaces
# 2. Create the kvm cmd line to connect to said interfaces
# 3. Create the guestfish cmd line to modify the vm to reflect the interfaces

i=1
KVMDEV=""
GUESTFISHDEV=""
for IFNAME in $($MNS ls /sys/class/net/); do
  if [[ ${IFNAME} == "lo" ]]; then
    continue
  fi
  VTAPNAME=${VTAPPREFIX}$i

  echo "Doing ${IFNAME} -> ${VTAPNAME}"
  $MNS ip link add link ${IFNAME} name ${VTAPNAME} type macvtap mode bridge
  #sleep 2
  $MNS ip link set dev ${VTAPNAME} up

  IFIP=$($MNS ip -f inet addr show ${IFNAME} | grep -Po 'inet \K[\d.]+')
  VTAPID=$($MNS cat /sys/class/net/${VTAPNAME}/ifindex)

  IP="${IFIP%.*}.3"
  NET="${IFIP%.*}.0/24"
  NM="255.255.255.0"
  GW="${IFIP%.*}.1"
  MAC=$($MNS cat /sys/class/net/${VTAPNAME}/address)
  NAME=${IFNAME}
  MARK=$((i + 1000))
  exec {FD}<>/dev/tap${VTAPID}

  KVMDEV="$KVMDEV \
          -device virtio-net-pci,netdev=net$i,mac=${MAC} \
          -netdev tap,id=net$i,fd=${FD}"
  GUESTFISHDEV="$GUESTFISHDEV
sh \"/bin/sed -e 's/##NAME##/${NAME}/g' /etc/network/netdev-template > /etc/network/interfaces.d/${IFNAME}\"
sh \"/bin/sed -i -e 's/##IP##/${IP}/g' /etc/network/interfaces.d/${IFNAME}\"
sh \"/bin/sed -i -e 's/##NM##/${NM}/g' /etc/network/interfaces.d/${IFNAME}\"
sh \"/bin/sed -e 's/##MAC##/${MAC}/g' -e 's/##NAME##/${NAME}/g' /etc/network/persistent-net.rules-template >> /etc/udev/rules.d/70-persistent-net.rules\"
sh \"/bin/echo 'ip rule add from ${IP} table ${MARK} pref 10000' >> /opt/monroe/setup-routing.sh\"
sh \"/bin/echo 'ip rule add dev lo table ${MARK} pref 40000' >> /opt/monroe/setup-routing.sh\"
sh \"/bin/echo 'ip route del ${NET} dev ${IFNAME} scope link' >> /opt/monroe/setup-routing.sh\"
sh \"/bin/echo 'ip route add ${NET} dev ${IFNAME} src ${IP} scope link table ${MARK}' >> /opt/monroe/setup-routing.sh\"
sh \"/bin/echo 'ip route add default via ${GW} src ${IP} table ${MARK}' >> /opt/monroe/setup-routing.sh\""
  i=$((i + 1))
done

# Add the mounts, these must correspond betwen vm and kvm cmd line
declare -A mounts=( [results]=$BASEDIR/$SCHEDID [config-dir]=$BASEDIR/$SCHEDID-conf/ )
for m in "${!mounts[@]}"; do
  OPT=",readonly"
  p=${mounts[$m]}
  if [ ! -d "${p}" ]; then
  	echo "Missing ${m} directory (${p}), exiting"
	exit 1
  fi
  if [[ "${m}" == "results" ]]; then
    OPT=""
  fi
  KVMDEV="$KVMDEV \
         -fsdev local,security_model=mapped,id=${m},path=${p}${OPT} \
         -device virtio-9p-pci,fsdev=${m},mount_tag=${m}"
  GUESTFISHDEV="$GUESTFISHDEV
sh \"/bin/echo '${m} /monroe/${m} 9p trans=virtio 0 0' >> /etc/fstab\"
sh \"/bin/mkdir -p /monroe/${m}\""
done


# Modify the vm image to reflect the current interface setup
guestfish -x <<-EOF
add ${disk_image}
run
mount /dev/sda1 /
sh "/bin/echo 9p >> /etc/initramfs-tools/modules"
sh "/bin/echo 9pnet >> /etc/initramfs-tools/modules"
sh "/bin/echo 9pnet_virtio >> /etc/initramfs-tools/modules"
sh "/usr/sbin/update-initramfs -u"
sh "/usr/sbin/grub-install --recheck --no-floppy /dev/sda"
sh "/usr/sbin/grub-mkconfig -o /boot/grub/grub.cfg"
${GUESTFISHDEV}
EOF
echo ${KVMDEV}
sleep 5
kvm -curses -m 1048 -hda ${disk_image} ${KVMDEV}
