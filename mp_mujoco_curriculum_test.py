from __future__ import division
import multiprocessing
import os
import os.path
import yaml, collections, io
import sys
import itertools
import signal
import random
from datetime import datetime

from ddpg import parse_args, cfg_run

random.seed(datetime.now())

# Usage:
# options = [flatten(tupl) for tupl in options]
def flatten(x):
    if isinstance(x, collections.Iterable):
        return [a for i in x for a in flatten(i)]
    else:
        return [x]

def main():
    alg = 'ddpg'
    args = parse_args()

    if args['cores']:
        arg_cores = min(multiprocessing.cpu_count(), args['cores'])
    else:
        arg_cores = min(multiprocessing.cpu_count(), 32)
    print('Using {} cores.'.format(arg_cores))

    # Parameters
    runs = range(10)
    reassess_for = ['']

    env = 'Walker2d2'
    e100 = "{}100".format(env)
    e150 = "{}150".format(env)
    e200 = "{}200".format(env)
    e250 = "{}250".format(env)

    #####
    # Curriculum
    keys   = (e100,     e150,     e200,     e250)
    bsteps = {e100:100, e150:150, e200:200, e250:250}
    steps  = {e100:700, e150:700, e200:700, e250:700}
    rb_names = {}
    for key in bsteps:
        rb_names[key] = "ddpg-{}_balancing-{:06d}-1010".format(key, int(round(100000*bsteps[key])))
    wsteps = {}
    for key in bsteps:
        wsteps[key] = steps[key] - bsteps[key]

    L0, L1, L2, L3 = [], [], [], []

    options = []
    for r in itertools.product([700], reassess_for, runs): options.append(r)
    configs = {
                "{}_walking".format(env) : "Roboschool{}GRL-v1".format(env),
              }
    L1 += rl_run(configs, alg, options)
    #####

    for key in keys:
        ## Zero-shot balancing Walker2d
        options = []
        for r in itertools.product([bsteps[key]], reassess_for, runs): options.append(r)

        configs = {
                    "{}_balancing".format(key) : "Roboschool{}BalancingGRL-v1".format(env),
                  }
        L0 += rl_run(configs, alg, options, rb_save=True)
        ####


        options = []
        for r in itertools.product([wsteps[key]], reassess_for, runs): options.append(r)
        configs = {
                    "{}_walking_after_balancing".format(key) : "Roboschool{}GRL-v1".format(env),
                  }
        L2 += rl_run(configs, alg, options, load_file=rb_names[key])
        ####

        reassess_for = ['']
        options = []
        for r in itertools.product([wsteps[key]], reassess_for, runs): options.append(r)
        configs = {
                    "{}_walking_after_balancing".format(key) : "Roboschool{}GRL-v1".format(env),
                  }
        L3 += rl_run(configs, alg, options, load_file=rb_names[key], rb_load=rb_names[key])

    ####
    do_multiprocessing_pool(arg_cores, L0)
    L = L1 + L2 + L3
    random.shuffle(L)
    do_multiprocessing_pool(arg_cores, L)

######################################################################################
def opt_to_str(opt):
    str_o = ''
    for  o in opt[:-1]:  # last element in 'o' is reserved for mp
        try:
            fl = float(o) # converts to float numbers and bools
            str_o += "-{:06d}".format(int(round(100000*fl)))
        except ValueError:
            if o: # skip empty elements, e.g. ""
                str_o +='-' + o
    if str_o:
        str_o = str_o[1:]
    return str_o

######################################################################################
def rl_run(dict_of_cfgs, alg, options, save=True, load_file='', rb_save=False, rb_load=''):
    list_of_new_cfgs = []

    loc = "tmp"
    if not os.path.exists(loc):
        os.makedirs(loc)

    for key in dict_of_cfgs:
        args = parse_args()
        cfg = dict_of_cfgs[key]

        for o in options:
            str_o = opt_to_str(o)
            str_o += '-' + boolList2BinString([save, bool(load_file), rb_save, bool(rb_load)])
            if not str_o:
                str_o += "mp{}".format(o[-1])
            else:
                str_o += "-mp{}".format(o[-1])
            print("Generating parameters: {}".format(str_o))

            # create local filename
            list_of_new_cfgs.append( "{}/{}-{}-{}.yaml".format(loc, alg, key, str_o) )

            args['cfg'] = cfg
            args['steps'] = o[0]*1000
            args['rb_max_size'] = args['steps']
            args['reassess_for'] = o[1]
            args['save'] = save

            if load_file:
                args['load_file'] = "{}-mp{}".format(load_file, o[-1])

            args['output'] = "{}-{}-{}".format(alg, key, str_o)

            if rb_save:
                args['rb_save_filename'] = args['output']

            if rb_load:
                args['rb_load_filename'] = "{}-mp{}".format(rb_load, o[-1])

            # Threads start at the same time, to prevent this we specify seed in the configuration
            args['seed'] = int.from_bytes(os.urandom(4), byteorder='big', signed=False) // 2
            with io.open(list_of_new_cfgs[-1], 'w', encoding='utf8') as file:
                yaml.dump(args, file, default_flow_style=False, allow_unicode=True)

    print(list_of_new_cfgs)
    return list_of_new_cfgs


######################################################################################
def mp_run(cfg):
    print('mp_run of {}'.format(cfg))
    # Read configuration
    try:
        file = open(cfg, 'r')
    except IOError:
        print("Could not read file: {}".format(cfg))
        sys.exit()
    with file:
        args = yaml.load(file)

    # Run the experiment
    try:
        cfg_run(**args)
    except Exception:
        print('mp_run {} failid to exit correctly'.format(cfg))
        sys.exit()


######################################################################################
def do_multiprocessing_pool(arg_cores, list_of_new_cfgs):
    """Do multiprocesing"""
    cores = multiprocessing.Value('i', arg_cores)
    print('cores {0}'.format(cores.value))
    original_sigint_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
    pool = multiprocessing.Pool(arg_cores)
    signal.signal(signal.SIGINT, original_sigint_handler)
    try:
        pool.map(mp_run, list_of_new_cfgs)
    except KeyboardInterrupt:
        pool.terminate()
    else:
        pool.close()
    pool.join()


######################################################################################
def boolList2BinString(lst):
    return ''.join(['1' if x else '0' for x in lst])


######################################################################################
if __name__ == "__main__":
    main()

