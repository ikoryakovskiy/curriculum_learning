#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Feb 23 08:53:20 2018

@author: ivan
"""
import time
import numpy as np
import pickle

from skopt import Optimizer
from skopt.learning import GaussianProcessRegressor
from skopt.space import Real

class opt_bo(object):
    def __init__(self, config, w_num, popsize):
        self.popsize = popsize
        self.optimizer = Optimizer(
            dimensions=[Real(-1.0, 1.0)] * w_num,
            random_state=1, # use the same seed for repeatability
            n_initial_points=self.popsize,
            acq_optimizer_kwargs = {'n_points':10000} # 'n_jobs' slows down, 'noise' seem not to be used
        )

    def stop(self):
        return False

    def ask(self):
        return self.optimizer.ask(n_points=self.popsize)

    def tell(self, solutions, damage):
        tell_time = time.time()
        res = self.optimizer.tell(solutions, damage)
        print('tell time: {}s'.format(time.time() - tell_time))
        return res

    def reeval(self, g, solutions, damage, hp):
        pass

    def log(self, root, alg, g, damage_info, reeval_damage_info):
        ibest = np.argmin(self.optimizer.yi)

        with open('{}/opt_bo.txt'.format(root), 'w') as f:
            for p in zip(self.optimizer.Xi,self.optimizer.yi):
                f.write(str(p)+'\n')

        with open('{}/{}-g{:04}.txt'.format(root, alg, g), 'w') as f:
            f.write(str(self.optimizer.yi[ibest])+'\n')
            f.write(str(self.optimizer.Xi[ibest])+'\n\n\n')

            for i, di in enumerate(damage_info):
                f.write('{:2d}'.format(i).rjust(3) + ': ' +  str(di) + '\n')

    def save(self, root, fname):
        with open(root+'/'+fname, 'wb') as f:
            pickle.dump(self.optimizer, f)

    def load(self, root, fname):
        with open(root+'/'+fname, 'rb') as f:
            self.optimizer = pickle.load(f)

