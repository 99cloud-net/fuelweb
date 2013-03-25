# -*- coding: utf-8 -*-

from nailgun.db import orm
from nailgun.logger import logger


class VolumeManager(object):

    def __init__(self, node):
        self.db = orm()
        self.node = node
        if not self.node:
            raise Exception(
                "Invalid node - can't generate volumes info"
            )
        self.volumes = []

    def _traverse(self, cdict):
        new_dict = {}
        if isinstance(cdict, dict):
            for i, val in cdict.iteritems():
                if type(val) in (str, unicode, int, float):
                    new_dict[i] = val
                elif isinstance(val, dict):
                    if "generator" in val:
                        new_dict[i] = self.field_generator(
                            val["generator"],
                            val.get("generator_args", [])
                        )
                    else:
                        new_dict[i] = self._traverse(val)
                elif isinstance(val, list):
                    new_dict[i] = []
                    for d in val:
                        new_dict[i].append(self._traverse(d))
        elif isinstance(cdict, list):
            new_dict = []
            for d in cdict:
                new_dict.append(self._traverse(d))
        return new_dict

    def field_generator(self, generator, args=None):
        if not args:
            args = []
        generators = {
            # swap = memory + 1Gb
            "calc_swap_size": lambda:
            self.node.meta["memory"]["total"] + 1024 ** 3,
            # root = 10Gb
            "calc_root_size": lambda: 1024 ** 3 * 10,
            "calc_boot_size": lambda: 1024 ** 2 * 200,
            # let's think that size of mbr is 1Mb
            "calc_mbr_size": lambda: 1024 ** 2,
            "calc_lvm_meta_size": lambda: 1024 ** 2 * 64
        }
        generators["calc_os_size"] = lambda: sum([
            generators["calc_root_size"](),
            generators["calc_swap_size"]()
        ])
        return generators.get(generator, lambda: None)(*args)

    def gen_volumes_info(self):
        if not "disks" in self.node.meta:
            raise Exception("No disk metadata specified for node")
        logger.debug(
            "Generating volumes info for node '{0}' (role:{1})".format(
                self.node.name or self.node.mac or self.node.id,
                self.node.role
            )
        )
        self.volumes = self.gen_default_volumes_info()
        if not self.node.cluster:
            return self.volumes
        volumes_metadata = self.node.cluster.release.volumes_metadata
        self.volumes = filter(
            lambda a: a["type"] == "disk",
            self.volumes
        )
        self.volumes.extend(
            volumes_metadata[self.node.role]
        )
        self.volumes = self._traverse(self.volumes)
        return self.volumes

    def gen_default_volumes_info(self):
        self.volumes = []
        if not "disks" in self.node.meta:
            raise Exception("No disk metadata specified for node")
        for disk in self.node.meta["disks"]:
            self.volumes.append(
                {
                    "id": disk["disk"],
                    "type": "disk",
                    "size": disk["size"],
                    "volumes": [
                        {"type": "pv", "vg": "os", "size": 0},
                        {"type": "pv", "vg": "vm", "size": 0},
                        {"type": "pv", "vg": "cinder", "size": 0}
                    ]
                }
            )

        # minimal space for OS + boot
        os_size = self.field_generator("calc_os_size")
        boot_size = self.field_generator("calc_boot_size")
        mbr_size = self.field_generator("calc_mbr_size")
        lvm_meta_size = self.field_generator("calc_lvm_meta_size")

        free_space = sum([
            disk["size"] - mbr_size
            for disk in self.node.meta["disks"]
        ])

        if free_space < (os_size + boot_size):
            raise Exception("Insufficient disk space for OS")

        def create_boot_sector(v):
            v["volumes"].append(
                {
                    "type": "partition",
                    "mount": "/boot",
                    "size": {"generator": "calc_boot_size"}
                }
            )
            # let's think that size of mbr is 2Mb (more than usual, for safety)
            v["volumes"].append(
                {"type": "mbr"}
            )

        os_vg_size_left = os_size
        ready = False
        for i, disk in enumerate(self.volumes):
            if disk["type"] != "disk":
                continue
            # current hard disk size - mbr size
            free_disk_space = disk["size"] - mbr_size

            if i == 0 and free_disk_space > (
                os_vg_size_left + boot_size + lvm_meta_size
            ):
                # all OS and boot on first disk
                disk["volumes"][0]["size"] = os_vg_size_left + lvm_meta_size
                create_boot_sector(disk)
                free_disk_space = free_disk_space - (
                    disk["volumes"][0]["size"] + boot_size
                )
                ready = True
            elif i == 0:
                # first disk: boot + part of OS
                disk["volumes"][0]["size"] = free_disk_space - boot_size
                create_boot_sector(disk)
                free_disk_space = 0
                os_vg_size_left = os_vg_size_left - (
                    disk["volumes"][0]["size"] - lvm_meta_size
                )
            elif free_disk_space > (os_vg_size_left + lvm_meta_size):
                # another disk: remaining OS
                disk["volumes"][0]["size"] = os_vg_size_left + lvm_meta_size
                free_disk_space = free_disk_space - disk["volumes"][0]["size"]
                ready = True
            else:
                # another disk: part of OS
                disk["volumes"][0]["size"] = free_disk_space
                os_vg_size_left = os_vg_size_left - (
                    disk["volumes"][0]["size"] - lvm_meta_size
                )
                free_disk_space = 0

            info = [
                mbr_size,
                boot_size,
                disk["volumes"][0]["size"]
            ]
            logger.debug(
                "Disk '{0}' space ({1} total): "
                "| {2} MBR | {3} BOOT | {4} OS |".format(
                    disk["id"],
                    sum(info),
                    *info
                )
            )

            if ready:
                break

        # creating volume groups
        self.volumes.extend([
            {
                "id": "os",
                "type": "vg",
                "volumes": [
                    {
                        "mount": "/",
                        "size": {"generator": "calc_root_size"},
                        "name": "root",
                        "type": "lv"
                    },
                    {
                        "mount": "swap",
                        "size": {"generator": "calc_swap_size"},
                        "name": "swap",
                        "type": "lv"
                    }
                ]
            },
            {
                "id": "vm",
                "type": "vg",
                "volumes": [
                    {"mount": "/var/lib/libvirt", "size": 0,
                     "name": "vm", "type": "lv"}
                ]
            }
        ])

        return self._traverse(self.volumes)