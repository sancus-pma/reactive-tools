import argparse
import logging
import asyncio
import pdb
import sys
import binascii

from . import config


def _setup_logging(args):
    if args.debug:
        level = logging.DEBUG
    elif args.verbose:
        level = logging.INFO
    else:
        level = logging.WARNING

    err_handler = logging.StreamHandler(sys.stderr)
    err_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    err_handler.setLevel(logging.WARNING)
    logging.root.addHandler(err_handler)

    class InfoFilter(logging.Filter):
        def filter(self, record):
            return record.levelno < logging.WARNING

    info_handler = logging.StreamHandler(sys.stdout)
    info_handler.setFormatter(logging.Formatter('%(message)s'))
    info_handler.setLevel(logging.INFO)
    info_handler.addFilter(InfoFilter())
    logging.root.addHandler(info_handler)

    logging.root.setLevel(level)


def _setup_pdb(args):
    if args.debug:
        sys.excepthook = \
                lambda type, value, traceback: pdb.post_mortem(traceback)


def _parse_args(args):
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--verbose',
        help='Verbose output',
        action='store_true')
    parser.add_argument(
        '--debug',
        help='Debug output and open PDB on uncaught exceptions',
        action='store_true')

    subparsers = parser.add_subparsers(dest='command')
    # Workaround a Python bug. See http://bugs.python.org/issue9253#msg186387
    subparsers.required = True

    deploy_parser = subparsers.add_parser(
        'deploy',
        help='Deploy a reactive network')
    deploy_parser.set_defaults(command_handler=_handle_deploy)
    deploy_parser.add_argument(
        'config',
        help='Configuration file describing the network')
    deploy_parser.add_argument(
        '--result',
        help='File to write the resulting configuration to')
    deploy_parser.add_argument(
        '--deploy-in-order',
        help='Deploy modules in the order they are found in the config file',
        action='store_true')

    call_parser = subparsers.add_parser(
        'call',
        help='Call a deployed module')
    call_parser.set_defaults(command_handler=_handle_call)
    call_parser.add_argument(
        '--config',
        help='Specify configuration file to use '
             '(the result of a previous "deploy" run)',
        required=True)
    call_parser.add_argument(
        '--module',
        help='Name of the module to call',
        required=True)
    call_parser.add_argument(
        '--entry',
        help='Name of the module\'s entry point to call',
        required=True)
    call_parser.add_argument(
        '--arg',
        help='Argument to pass to the entry point (hex byte array)',
        type=binascii.unhexlify,
        default=None)

    return parser.parse_args(args)


def _handle_deploy(args):
    logging.info('Deploying %s', args.config)

    conf = config.load(args.config)

    if args.deploy_in_order:
        conf.deploy_modules_ordered()

    conf.install()

    if args.result is not None:
        logging.info('Writing post-deployment configuration to %s', args.result)
        config.dump(conf, args.result)


def _handle_call(args):
    logging.info('Calling %s:%s', args.module, args.entry)

    conf = config.load(args.config)
    module = conf.get_module(args.module)

    asyncio.get_event_loop().run_until_complete(
                                            module.call(args.entry, args.arg))


def main(raw_args=None):
    args = _parse_args(raw_args)

    _setup_logging(args)
    _setup_pdb(args)

    try:
        args.command_handler(args)
    except BaseException as e:
        if args.debug:
            raise

        logging.error(e)
        return 1
    finally:
        # If we don't close the event loop explicitly, there is an unhandled
        # exception being thrown from its destructor. Not sure why but closing
        # it here prevents annoying noise.
        asyncio.get_event_loop().close()

