SOURCE_DIR?=$(dir $(lastword $(MAKEFILE_LIST)))
SOURCE_DIR:=$(abspath $(SOURCE_DIR))
TOP_DIR?=$(PWD)
TOP_DIR:=$(abspath $(TOP_DIR))
BUILD_DIR?=$(TOP_DIR)/build
BUILD_DIR:=$(abspath $(BUILD_DIR))
LOCAL_MIRROR?=$(TOP_DIR)/local_mirror
LOCAL_MIRROR:=$(abspath $(LOCAL_MIRROR))
DEPV_DIR?=$(BUILD_DIR)/depv
DEPV_DIR:=$(abspath $(DEPV_DIR))

.PHONY: all clean test help deep_clean

help:
	@echo 'Build directives (can be overrided by environment variables'
	@echo 'or by command line parameters):'
	@echo '  SOURCE_DIR: $(SOURCE_DIR)'
	@echo '  BUILD_DIR: $(BUILD_DIR)'
	@echo '  LOCAL_MIRROR: $(LOCAL_MIRROR)'
	@echo '  YUM_REPOS: $(YUM_REPOS)'
	@echo '  MIRROR_CENTOS: $(MIRROR_CENTOS)'
	@echo '  MIRROR_EGGS: $(MIRROR_EGGS)'
	@echo '  MIRROR_GEMS: $(MIRROR_GEMS)'
	@echo '  MIRROR_SRC: $(MIRROR_SRC)'
	@echo
	@echo 'Available targets:'
	@echo '  all  - build product'
	@echo '  bootstrap  - build bootstrap'
	@echo '  iso  - build iso image'
	@echo '  img  - build flash stick image'
	@echo '  test - run all tests'
	@echo '  test-unit - run unit tests'
	@echo '  test-integration - run integration tests'
	@echo '  test-integration-env - prepares integration test environment'
	@echo '  clean-integration-test - clean integration test environment'
	@echo '  clean - remove build directory and resetting .done flags'
	@echo '  deep_clean - clean + removing $(LOCAL_MIRROR) directory'
	@echo '  distclean - cleans deep_clean + clean-integration-test'
	@echo
	@echo 'To build system using one of the proprietary mirrors use '
	@echo 'the following commands:'
	@echo
	@echo 'Saratov office (default):'
	@echo 'make iso'
	@echo
	@echo 'Moscow office:'
	@echo 'make iso USE_MIRROR=msk'
	@echo
	@echo 'Custom location:'
	@echo 'make iso YUM_REPOS=proprietary \
MIRROR_CENTOS=http://<your_mirror>/centos \
MIRROR_EGGS=http://<your_mirror>/eggs \
MIRROR_GEMS=http://<your_mirror>/gems \
MIRROR_SRC=http://<your_mirror>/src'

all: iso

test: test-unit test-integration

clean:
	sudo rm -rf $(BUILD_DIR)
deep_clean: clean
	sudo rm -rf $(LOCAL_MIRROR)

distclean: deep_clean clean-integration-test

include $(SOURCE_DIR)/rules.mk

# Common configuration file.
include $(SOURCE_DIR)/config.mk

# Sandbox macroses.
include $(SOURCE_DIR)/sandbox.mk

# Modules
include $(SOURCE_DIR)/mirror/module.mk
include $(SOURCE_DIR)/packages/module.mk
include $(SOURCE_DIR)/bootstrap/module.mk
include $(SOURCE_DIR)/iso/module.mk
include $(SOURCE_DIR)/fuelweb_test/module.mk
