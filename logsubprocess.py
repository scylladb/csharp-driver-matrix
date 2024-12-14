import logging
import os
import subprocess


def dry_run():
    return os.getenv('DRY_RUN') == 'true'


def wrap(attribute_name):
    original = getattr(subprocess, attribute_name)

    def _wrapped_in_logging(* args, ** kwargs):
        if isinstance(args[0], list):
            command_string = ' '.join(args[0])
        else:
            command_string = args[0]
        logging.info('%s: %s', attribute_name, command_string)
        if dry_run():
            return original(['true'])
        return original(* args, ** kwargs)

    setattr(subprocess, attribute_name, _wrapped_in_logging)


wrap('Popen')
