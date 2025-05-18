#!/usr/bin/env python3

from subprocess import Popen, PIPE
from dataclasses import dataclass, fields

import calendar
import configparser
import datetime
import functools
import json
import os
import socket
import sys


class attrdict(dict):
    def __getattr__(self, k):
        return self.__dict__.get(k, self.get(k))


@dataclass
class Issue:
    name: str
    description: str
    ext: any = None


@dataclass
class Node:
    cpu: float
    disk: str
    id: str
    level: str
    maxcpu: int
    maxdisk: int
    maxmem: int
    mem: int
    node: str
    ssl_fingerprint: str
    status: str
    type: str
    uptime: int


@dataclass
class VM:
    parent_node: Node
    cpu: int
    cpus: int
    disk: int
    diskread: int
    diskwrite: int
    maxdisk: int
    maxmem: int
    mem: int
    name: str
    netin: int
    netout: int
    status: str
    uptime: int
    vmid: int
    pid: str = None
    lock: str = None
    template: str = None
    serial: int = None

@dataclass
class VMConfig:
    parent_node: Node
    vm: VM
    config: attrdict


def make_object(cls, d):
    return cls(**{x.name: d.get(x.name) for x in fields(cls)})


class PVESHWrapper():
    def __init__(self):
        self.nodes = self.get_nodes()
        self.qemu_vms = self.get_qemu_vms()

    @functools.lru_cache(None)
    def wrapped(self, command: str, argument: str) -> dict:
        with Popen(["pvesh", command, argument, "--output-format=json"], stdout=PIPE) as proc:
            return json.loads(proc.stdout.read().decode())

    def get_nodes(self):
        data = []
        nodes = self.wrapped("get", "/nodes/")
        for node in nodes:
             data.append(Node(**node))
        return data

    def get_qemu_vms(self, just_mine=True):
        data = []

        nodes = self.nodes
        if just_mine:
            me = socket.gethostname().split(".")[0]
            nodes = [i for i in nodes if i.node == me]

        if not nodes:
            raise ValueError("No applicable nodes")

        for node in nodes:
            vms = self.wrapped("get", f"/nodes/{node.node}/qemu")
            for vm in vms:
                data.append(VM(parent_node=node, **vm))

        return sorted(data, key=lambda i: i.vmid)

    def get_vmid_config(self, node: Node, vm: VM) -> VMConfig:
        config = self.wrapped("get", f"/nodes/{node.node}/qemu/{vm.vmid}/config")
        return VMConfig(node, vm, attrdict(config))

    def get_storage_config(self):
        storage = self.wrapped("get", "/storage")
        for store in storage:
            yield attrdict(store)

    def get_storage_by_name(self, name):
        storage = self.wrapped("get", f"/storage/{name}")
        return attrdict(storage)

    def get_backups(self):
        backup = self.wrapped("get", "/cluster/backup")
        for ret in backup:
            yield attrdict(ret)


def verify_onboot_running(wrapper: PVESHWrapper) -> list:
    for vm in wrapper.qemu_vms:
        config = wrapper.get_vmid_config(vm.parent_node, vm)
        if config.config.onboot == 1 and vm.status != "running":
            yield Issue(name="vm:stopped",
                        description=f"VM {config.vm.vmid} is stopped but is marked to start on boot",
                        ext={"vm": config.vm.vmid})

        elif config.config.onboot == 0 and vm.status == "running":
            yield Issue(name="vm:not_onboot",
                        description=f"VM {config.vm.vmid} is started but not marked to start on boot",
                        ext={"vm": config.vm.vmid})


def verify_storage(wrapper: PVESHWrapper):
    lvm_has_images_and_rootdir = False
    lvm_exists = False

    lvm_allow = ["images", "rootdir"]
    nfs_smb_disallow = lvm_allow

    config = wrapper.get_storage_config()
    configs = [attrdict(c) for c in config]
    for conf in configs:
        # Ensures zfs storage does not exist
        if conf.type == "zfspool":
            yield Issue(name="storage:is_zfs",
                        description=f"Storage {conf.storage} is ZFS.",
                        ext={"storage": conf.storage})

        # Ensures at least one LVM or LVMThin exists, and if they do that they have images and rootdir
        if conf.type == "lvm" or conf.type == "lvmthin":
            lvm_exists = True
            if set(conf.content.split(",")) != set(lvm_allow):
                yield Issue(name="storage:invalid_content",
                            description=f"{conf.storage} does not allow content rootdir,images exactly",
                            ext={"storage": conf.storage})

        # checks if storage has NFS or SMB, and if any content matches the disallow
        if conf.type == "nfs" or conf.type == "smb":
            disallowed_fields = [a for a in nfs_smb_disallow if a in conf.content]
            if disallowed_fields:
                disallowed_fields = ",".join(disallowed_fields)
                yield Issue(name="storage:invalid_content",
                            description=f"{conf.storage} allows content {disallowed_fields}.",
                            ext={"storage": conf.storage})

        if conf.storage == "local":
            if any(a in conf.content for a in lvm_allow):
                yield Issue(name="storage:invalid_content",
                            description=f"Local storage supports {conf.content} which is not allowed.",
                            ext={"storage": conf.storage})

    if not lvm_exists:
        yield Issue(name="storage:no_lvm", description=f"No LVM storage found.")


def determine_boot(wrapper: PVESHWrapper):
    for vm in wrapper.qemu_vms:
        config = wrapper.get_vmid_config(vm.parent_node, vm)

        bootdisk = config.config.bootdisk
        if bootdisk is None:
            boot = config.config.boot
            if boot is None:
                continue

            if "=" not in boot:
                yield Issue(name="vm:storage:unparseable_bootdisk",
                            description=f"VM {config.vm.vmid} has an invalid bootdisk",
                            ext={"vm": config.vm.vmid})
                continue

            bootdisk = boot.split("=")[1].split(",")[0]

        if not bootdisk:
            yield Issue(name="vm:storage:bootdisk_missing", description=f"VM {config.vm.vmid} doesn't have a boot device defined")
            continue

        start = bootdisk.split(",")[0]
        if not hasattr(config.config, start):
            yield Issue(name="vm:storage:bootdisk_invalid", description=f"VM {config.vm.vmid} first boot device doesn't exist")
            continue

        diskname = start.split(";")[0]
        bootdisk = getattr(config.config, diskname)
        storage = bootdisk.split(":")[0]

        if "none" in storage:
            continue

        store = wrapper.get_storage_by_name(storage)

        if any([a in store.type for a in ["nfs", "cifs"]]):
            yield Issue(name="vm:storage:nfs",
                        description=f"VM {config.vm.vmid} has a boot disk on {store.type} storage",
                        ext={"vm": config.vm.vmid})


def determine_backup(wrapper: PVESHWrapper):
    backup_data = wrapper.get_backups()
    if not backup_data:
        return

    found_nfs = False

    for data in backup_data:
        if not data.enabled:
            yield Issue(name="backup:disabled", description="A backup schedule is disabled.")
            continue

        include = []
        if hasattr(data, "vmid"):
            include = data.vmid

        if isinstance(include, str):
            include = include.split(",")
            include = [int(i) for i in include]

        exclude = []
        if hasattr(data, "exclude") and data.exclude is not None:
            exclude = data.exclude

            if isinstance(exclude, str):
                exclude = exclude.split(",")

            exclude = [int(i) for i in exclude]

        if not include:
            include = [x.vmid for x in wrapper.get_qemu_vms() if x.vmid not in exclude]

        vmids = [int(x.vmid) for x in wrapper.get_qemu_vms()]
        include = [i for i in include if int(i) in vmids]

        storage = wrapper.get_storage_by_name(data.storage)
        if storage.type in {"cifs", "nfs"}:
            found_nfs = True

        if os.path.exists(storage.path):
            dumps = os.path.join(storage.path, "dump")
            if not os.path.exists(dumps):
                continue

            files = os.listdir(dumps)

            for vm in include:
                found = False
                latest = datetime.datetime(year=1, month=1, day=1)

                # Find Latest Backup
                for f in files:
                    if not f.endswith(".log"):
                        continue

                    fdata = f.split(".")[0].split("-")
                    if len(fdata) != 5:
                        continue

                    if not fdata[2].isnumeric() or int(fdata[2]) != int(vm):
                        continue

                    backup_date = datetime.datetime.strptime(
                        fdata[3] + "T" + fdata[4], "%Y_%m_%dT%H_%M_%S")

                    if backup_date > latest:
                        found = True
                        latest = backup_date
                        latest_file = f

                # No backup found for VM
                if not found:
                    yield Issue(name="backup:no_backup",
                                description=f"VM {vm} has backups enabled, but has yet to create a backup.",
                                ext={"vm": vm, "storage": data.storage})

                    continue

                with open(os.path.join(dumps, latest_file)) as f:
                    if "INFO: Finished Backup of VM" not in list(f)[-1]:
                        yield Issue(name="backup:failed",
                                    description=f"VM {vm} latest backup log {latest_file} does not indicate a successful backup")

                # Checking if the VM has been backed up in a reasonable amount of time previously.
                now = datetime.datetime.now()

                # if it was backed up today, its good :)
                if latest.date() == now.date():
                    continue

                timedelta = now - latest
                if isinstance(data.dow, list):
                    times_a_week = len(data.dow)
                elif data.dow is not None:
                    times_a_week = data.dow.count(",") + 1
                else:
                    times_a_week = 1

                if timedelta.days > max(4, 7 / times_a_week):
                    yield Issue(name="backup:too_old",
                                description=f"Latest backup on VM {vm} (at {latest.strftime('%Y-%m-%d')}) is too old",
                                ext={"vm": vm, "storage": data.storage})

    if not found_nfs:
        yield Issue(name="backup:no_network", description="No network backup schedule found.")

if __name__ == "__main__":
    issues = []
    wrapper = PVESHWrapper()

    config = configparser.ConfigParser()
    config.read("/etc/monitoring.ini")

    if len(sys.argv) > 1:
        area = sys.argv[1]

        if area == "backup":
            issues.extend(determine_backup(wrapper))
        elif area == "not-backup":
            issues.extend(verify_onboot_running(wrapper))
            issues.extend(verify_storage(wrapper))
            issues.extend(determine_boot(wrapper))

    else:
        issues.extend(verify_onboot_running(wrapper))
        issues.extend(verify_storage(wrapper))
        issues.extend(determine_boot(wrapper))
        issues.extend(determine_backup(wrapper))

    default_squelch = "storage:invalid_content"
    squelches_conf = config.get("proxmox", "squelch", fallback=default_squelch).split(",")
    squelches = []

    for squelch in squelches_conf:
        restricts = {}
        if "@" in squelch:
            squelch, restricts_str = squelch.split("@", maxsplit=1)
            for restrict in restricts_str.split(";"):
                k, v = restrict.split("=")
                restricts[k] = v

        squelches.append((squelch, restricts))

    resulting_issues = []
    for issue in issues:
        for squelch, restricts in squelches:
            if issue.name == squelch and all(issue.ext.get(k) == v for k, v in restricts.items()):
                break

        else:
            resulting_issues.append(issue)

    if not resulting_issues:
        print("PROXMOX OK - no issues found | issues=0")
        exit(0)

    print(f"PROXMOX WARNING - found configuration issues | issues={len(issues)}")
    print()

    for issue in resulting_issues:
        ext_str = ""
        if isinstance(issue.ext, dict):
            ext_str = " [" + ";".join(f"{k}={v}" for k, v in sorted(issue.ext.items())) + "]"

        print(f"{issue.name}{ext_str}")
        print(f"  {issue.description}")
        print()

    exit(1)
