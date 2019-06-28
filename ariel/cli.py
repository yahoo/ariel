# Copyright 2019, Oath Inc.
# Licensed under the terms of the Apache License, Version 2.0. See LICENSE file for terms.
import ariel
import importlib
import pkgutil
import sys

# Dynamic invocation of first argument
def cli():
    if len(sys.argv) == 1:
        usage()

    command = sys.argv[1].replace('-', '_')
    cli_ref = getCli(command)
    
    if cli_ref is None or cli_ref == cli:
        usage()

    cli_ref()

def usage():
    print("Usage: {} <command> [command specific]".format(sys.argv[0]))
    print("\nCommands:")
    for module in getCliModules():
        print("\t{}".format(module))
    print()
    sys.exit(1)

def getCli(command):
    try:
        if __package__ is not None:
            module = getattr(__import__(__package__, fromlist=[command]), command)
        else:
            module = importlib.import_module(command, package="ariel")
    except:
        return None
    
    if hasattr(module, 'cli'):
        return getattr(module, 'cli')
    return None

def getCliModules():
    moduleList = pkgutil.iter_modules(ariel.__path__)
    moduleList = filter(lambda m: m[1] != 'cli' and not m[1].startswith('_') and m[2] == False and getCli(m[1]) != None, moduleList)
    moduleList = map(lambda m: m[1], moduleList)
    return moduleList

if __name__ == '__main__':
    cli()
