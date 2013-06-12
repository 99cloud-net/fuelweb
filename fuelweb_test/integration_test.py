import os.path
import sys
import logging
import argparse
from nose.plugins.manager import PluginManager
from nose.plugins.xunit import Xunit
from root import root, REPOSITORY_ROOT


sys.path[:0] = [
    REPOSITORY_ROOT,
    root('devops'),
]

import fuelweb_test.integration


def main():
    parser = argparse.ArgumentParser(description="Integration test suite")
    parser.add_argument("-i", "--iso", dest="iso",
                        help="iso image path or http://url")
    parser.add_argument("-l", "--level", dest="log_level", type=str,
                        help="log level", choices=[
                            "DEBUG",
                            "INFO",
                            "WARNING",
                            "ERROR"
                        ],
                        default="ERROR", metavar="LEVEL")
    parser.add_argument('--no-forward-network', dest='no_forward_network',
                        action="store_true", default=False,
                        help='do not forward environment netork')
    parser.add_argument('--export-logs-dir', dest='export_logs_dir', type=str,
                        help='directory to save fuelweb logs')
    parser.add_argument('--installation-timeout', dest='installation_timeout',
                        type=int, help='admin node installation timeout')
    parser.add_argument('--deployment-timeout', dest='deployment_timeout',
                        type=int, help='admin node deployment timeout')
    parser.add_argument('--suite', dest='test_suite', type=str,
                        help='Test suite to run', choices=["integration"],
                        default="integration")
    parser.add_argument('--environment', dest='environment', type=str,
                        help='Environment name', default="integration")
    parser.add_argument('command', choices=('setup', 'destroy', 'test'),
                        default='test', help="command to execute")
    parser.add_argument(
        'arguments',
        nargs=argparse.REMAINDER,
        help='arguments for nose testing framework'
    )

    params = parser.parse_args()

    numeric_level = getattr(logging, params.log_level.upper())
    logging.basicConfig(level=numeric_level)
    paramiko_logger = logging.getLogger('paramiko')
    paramiko_logger.setLevel(numeric_level + 1)

    suite = fuelweb_test.integration

#   todo fix default values
    if params.no_forward_network:
        ci = suite.Ci(params.iso, forward=None, env_name=params.environment)
    else:
        ci = suite.Ci(params.iso, env_name=params.environment)

    if params.export_logs_dir is not None:
        ci.export_logs_dir = params.export_logs_dir

    if params.deployment_timeout is not None:
        ci.deployment_timeout = params.deployment_timeout

    if params.command == 'setup':
        result = ci.setup_environment()
    elif params.command == 'destroy':
        result = ci.destroy_environment()
    elif params.command == 'test':
        import nose
        import nose.config

        nc = nose.config.Config()
        nc.verbosity = 3
        nc.plugins = PluginManager(plugins=[Xunit()])
        # Set folder where to process tests
        nc.configureWhere(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                params.test_suite
            )
        )

        suite.ci = ci
        nose.main(module=suite, config=nc, argv=[
            __file__,
            "--with-xunit",
            "--xunit-file=nosetests.xml"
        ] + params.arguments)
        result = True
    else:
        print("Unknown command '%s'" % params.command)
        sys.exit(1)

    if not result:
        sys.exit(1)


if __name__ == "__main__":
    main()
