from __future__ import division
import numpy as np
import tensorflow as tf
import glob
import pickle
from sklearn.metrics import r2_score
import matplotlib.pyplot as plt

from replaybuffer_ddpg import ReplayBuffer
from critic import CriticNetwork
from cl_network import CurriculumNetwork

tf.logging.set_verbosity(tf.logging.INFO)

from ptracker import PerformanceTracker
from cl_network import CurriculumNetwork
from ddpg import parse_args

tt = 0 # duration
ee = 1 # td error
cc = 2 # complexity
ss = 3 # curriculum stage


def read_file(f, cl_mode=0):
    try:
        data = np.loadtxt(f, skiprows=3, usecols=(3, 11, 12, 4, 5))
    except IndexError:
        return None
    except Exception as e:
        print(e)
    length = data.shape[0]
    damage = data[:,3,np.newaxis]
    distance = data[:,4,np.newaxis]
    data = np.hstack((data[:,0:3], cl_mode*np.ones((length,1))))
    return {'data':data, 'damage':damage, 'distance':distance}


def concat(first, second, first_no_damage=0):
    if not first and not second: return None
    if not first: return second
    if not second: return first
    data = np.vstack((first['data'], second['data']))
    damage1 = (1-first_no_damage)*first['damage']
    damage2 = damage1[-1] + second['damage']
    damage = np.vstack((damage1, damage2))
    distance = np.vstack((first['distance'], second['distance']))
    return {'data':data, 'damage':damage, 'distance':distance}


def load_data(path, params, gmax = 1):
    stage_names = ('00_balancing_tf', '01_balancing', '02_walking')
    name_format = 'ddpg-g{:04d}-mp*-{stage_name}.monitor.csv'

    dd = []
    for g in range(1, 1+gmax):
        pat = path + name_format.format(g, stage_name=stage_names[0])
        for f in sorted(glob.glob(pat)):
            balancing_tf = read_file(f, cl_mode=0)
            balancing    = read_file(f.replace(stage_names[0], stage_names[1]), cl_mode=1)
            walking      = read_file(f.replace(stage_names[0], stage_names[2]), cl_mode=2)
            d = concat(balancing_tf, balancing)
            d = concat(d, walking)
            dd.append(d)
    return dd


def clean_dataset(dd, params):
    damamge_threshold = params['damamge_threshold']
    dd_new = []
    for d in dd:
        data = d['data']
        damage = d['damage']
        distance = d['distance']
        walked = any(distance > 10.0) # walked more then 10 m
        if walked and damamge_threshold and damage[-1] < damamge_threshold:
            if all(data[-1,1:] == data[-2,1:]): # last export was not due to the end of testing
                data = data[:-1, :]
                damage = damage[:-1, :]
            dd_new.append({'data': data, 'damage': damage})
    print('Percentage = {}'.format(len(dd_new)/len(dd)))
    return dd_new


def process_data(dd, config, params, zero_padding_after=1):
    steps_of_history = params['steps_of_history']
    dd_new = []
    for d in dd:
        norm_duration = d['data'][:, 0, np.newaxis] / config['env_timeout']
        norm_duration = np.vstack((np.zeros((steps_of_history, 1)), norm_duration))
        norm_duration = np.vstack((norm_duration, np.zeros((zero_padding_after, 1))))

        norm_td_error = d['data'][:, 1, np.newaxis] / config["env_td_error_scale"]
        norm_td_error = np.vstack((np.zeros((steps_of_history, 1)), norm_td_error))
        norm_td_error = np.vstack((norm_td_error, np.zeros((zero_padding_after, 1))))

        norm_complexity = d['data'][:, 2, np.newaxis]
        norm_complexity = np.vstack((np.zeros((steps_of_history, 1)), norm_complexity))
        norm_complexity = np.vstack((norm_complexity, np.zeros((zero_padding_after, 1))))

        cl_mode = (d['data'][:, 3, np.newaxis] + 1)/10
        cl_mode = np.vstack((np.ones((steps_of_history, 1))*cl_mode[0], cl_mode))
        cl_mode = np.vstack((cl_mode, np.zeros((zero_padding_after, 1))))

        data = np.hstack((norm_duration, norm_td_error, norm_complexity, cl_mode))

        damage = (d['damage'][-1] - d['damage']) / config['default_damage']
        damage0 = d['damage'][-1] / config['default_damage']
        damage = np.vstack((np.ones((steps_of_history, 1))*damage0, damage))
        damage = np.vstack((damage, np.zeros((zero_padding_after, 1)))) # No padding of damage?

        dd_new.append({'data': data, 'damage': damage})

    return dd_new

def normalize(data, mean_data=None, std_data=None):
    if mean_data is None:
        mean_data = np.mean(data, axis=0)
    if std_data is None:
        std_data = np.std(data, axis=0)
    norm_data = (data-mean_data[np.newaxis,:]) / std_data[np.newaxis,:]
    return norm_data, mean_data, std_data

def normalize_data(dd, config, params, data_norm=None, damage_norm=None):
    steps_of_history = params['steps_of_history']
    zero_padding_after = params['zero_padding_after']
    dd_new = []

    # normalize
    if data_norm is None or damage_norm is None:
        data = []
        damage = []
        for d in dd:
            data.append(d['data'])
            damage_ = d['damage'][-1] - d['damage']
            damage0 = np.array(d['damage'][-1])
            damage.append(np.vstack((damage0, damage_)))
        data, data_mean, data_std = normalize(np.concatenate(data))
        damage, damage_mean, damage_std = normalize(np.concatenate(damage))
        assert(len(np.where(~data.any(axis=1))[0]) == 0)    # assert no 0 rows in data, which is important for dynamic RNN
        assert(len(np.where(~damage.any(axis=1))[0]) == 0)
    else:
        data_mean, data_std = data_norm
        damage_mean, damage_std = damage_norm

    # apply normalization to each episode
    dim = len(data_mean)
    for d in dd:
        if params['indi_norm']:
            data, _, _ = normalize(d['data'], data_mean, data_std)
        else:
            data = d['data']
        data = np.vstack((np.zeros((steps_of_history, dim)), data, np.zeros((zero_padding_after, dim))))
        data[0:steps_of_history, 3] = data[steps_of_history, 3]

        if params['damage_norm'] == 'to_reward':
            damage = -np.diff(d['damage'], axis=0)
            damage = np.vstack((np.zeros((steps_of_history,1)), damage, np.zeros((1,1))))
        else:
            damage = (d['damage'][-1] - d['damage'])
            damage0 = d['damage'][-1]
            damage = np.vstack((np.ones((steps_of_history, 1))*damage0, damage))
            damage, _, _ = normalize(damage, damage_mean, damage_std)
        damage = np.vstack((damage, np.zeros((zero_padding_after, 1)))) # No padding of damage?

        stage = d['data'][:, ss, np.newaxis]
        if params['stage_norm'] == 'cetered':
            stage = stage - 1
        stage = np.vstack((np.ones((steps_of_history, 1))*stage[0], stage, -1*np.ones((zero_padding_after, 1))))

        dd_new.append({'data': data, 'damage': damage, 'stage':stage})

    return dd_new, (data_mean, data_std), (damage_mean, damage_std)


def seq_cut(dd, params, dim):
    steps_of_history = params['steps_of_history']
    data_ = []
    damage_ = []
    stage_ = []
    seq_data_ = []
    seq_damage_ = []
    for d in dd:
        data = d['data']
        damage = d['damage']
        stage = d['stage']
        for i in range(0, len(damage) - steps_of_history + 1):
            seq_data_.append(data[i:i+steps_of_history, :])
            seq_damage_.append(damage[i+steps_of_history-1]) #damage_ = damage[i:i+steps_of_history, :]
            data_.append(data[i+steps_of_history-1, :])
            damage_.append(damage[i+steps_of_history-1])
            stage_.append(stage[i+steps_of_history-1])

    seq_data_ = np.reshape(seq_data_, [-1, steps_of_history, dim])
    seq_damage_ = np.reshape(seq_damage_, [-1, 1])
    data_ = np.array(data_)
    damage_ = np.array(damage_)
    stage_ = np.array(stage_)

    min_data_ = np.min(data_, axis=0)
    med_data_ = np.median(data_, axis=0)
    max_data_ = np.max(data_, axis=0)
    min_damage_ = np.min(damage_, axis=0)
    med_damage_ = np.median(damage_, axis=0)
    max_damage_ = np.max(damage_, axis=0)
    print('Data stat:\n  {}\n  {}\n  {}\n  {}\n  {}\n  {}\n '.format(min_data_, med_data_, max_data_,
          min_damage_, med_damage_, max_damage_))
    return {'seq_data': seq_data_, 'seq_damage': seq_damage_, 'data': data_, 'damage': damage_, 'stage': stage_}

def fill_replay_buffer(dd, config):
    replay_buffer = ReplayBuffer(config, o_dims=cc+1)
    for d in dd:
        data = d['data']
        damage = d['damage']
        stage = d['stage']
        for i in range(len(damage)-1):
            terminal = 1 if i == len(damage)-2 else 0
            replay_buffer.replay_buffer_add(data[i, tt:cc+1], stage[i], damage[i], terminal, data[i+1, tt:cc+1])
    assert(replay_buffer.replay_buffer_count < config["rb_max_size"])
    return replay_buffer

def main():
    params = {}
    params['steps_of_history'] = 1
    params['zero_padding_after'] = 0
    params['damamge_threshold'] = 10000.0
    params['indi_norm'] = True
    params['damage_norm'] = 'to_reward'
    params['stage_norm'] = 'cetered'
    params['neg_damage'] = True
    dim = 4

    config = parse_args()
    config["cl_lr"] = 0.0001
    config['cl_structure'] = 'ffcritic:fc_relu_4;fc_relu_3;fc_relu_3'
    #config['cl_structure'] = 'ffcritic:fc_relu_2;fc_relu_2;fc_relu_1'
    config["cl_batch_norm"] = True
    config['cl_dropout_keep'] = 0.7
    config["cl_l2_reg"] = 0.001
    config["minibatch_size"] = 128

    dd = load_data('leo_supervised_learning_regression/', params, gmax = 6)

    # Rule-based processing before splitting
    dd = clean_dataset(dd, params)
    #dd = process_data(dd, config, params, zero_padding_after)

    # split into training and testing sets
    test_percentage = 0.3
    idx = np.arange(len(dd))
    np.random.shuffle(idx)
    test_idx = int(len(dd)*test_percentage)
    dd_train = [d for i,d in enumerate(dd) if i in idx[test_idx:]]
    dd_test = [d for i,d in enumerate(dd) if i in idx[:test_idx]]

    # normalize training dataset and use moments to normalizing test dataset
    dd_train, data_norm, damage_norm = normalize_data(dd_train, config, params)
    dd_test, _, _ = normalize_data(dd_test, config, params, data_norm, damage_norm)

    # get stat
    seq_cut(dd_train, params, dim)
    seq_cut(dd_test, params, dim)

    # fill in replay beuffer
    rb_train = fill_replay_buffer(dd_train, config)
    rb_test = fill_replay_buffer(dd_test, config)

    #config["minibatch_size"] = rb_train.replay_buffer_count

    with tf.Graph().as_default() as ddpg_graph:
        #pt = PerformanceTracker(depth=config['cl_depth'], input_norm=config["cl_input_norm"], dim=dim)
        #critic = CurriculumNetwork((params['steps_of_history'], pt.get_v_size()), config)
        critic = CurriculumNetwork(3, config)
        #critic_div = CriticNetwork(3, 1, config, 0)

    gpu_options = tf.GPUOptions(per_process_gpu_memory_fraction=0.15)
    x, td_error_, mb_td_error_, train_td_error_, test_td_error_ = [], [], [], [], []
    plt.ion()
    with tf.Session(graph=ddpg_graph, config=tf.ConfigProto(gpu_options=gpu_options)) as sess:

        # random initialization of variables
        sess.run(tf.global_variables_initializer())

        minibatch_size = config["minibatch_size"]
        for i in range(200000):
            s_batch, a_batch, r_batch, t_batch, s2_batch = rb_train.sample_batch(minibatch_size)

            # Calculate targets
            qq_val = []
            for stage in range(0,3):
                a_max = (stage-1)*np.ones((minibatch_size,1))
                qq_val.append(critic.predict_(sess, s2_batch, action=a_max))
            q_val = np.concatenate(qq_val, axis=1)
            q_max = np.max(q_val, axis=1)
            q_max = np.reshape(q_max,newshape=(minibatch_size,1))

            y_i = []
            for k in range(minibatch_size):
                if t_batch[k]:
                    y_i.append(r_batch[k])
                else:
                    y_i.append(r_batch[k] + config["gamma"] * q_max[k][0]) # target_q: list -> float

            if i%500 == 0:
                q_i = critic.predict_(sess, s_batch, action=a_batch)
                td_error = np.sum(np.abs(q_i-np.reshape(y_i,newshape=(minibatch_size,1)))) / minibatch_size

            critic.train(sess, s_batch, np.reshape(y_i, (minibatch_size,1)), action=a_batch)
            #critic_div.train(sess, s_batch, a_batch, np.reshape(y_i, (minibatch_size,1)))


            # testing
            if i%500 == 0:
                not_biases = [ v for v in critic.network.network_params if '/b:' not in v.name ]
                print(sess.run(not_biases))

                print(min(q_max))

                mb_td_error = calc_td_error(sess, critic, config, s_batch, a_batch, r_batch, t_batch, s2_batch, minibatch_size)

                s_batch, a_batch, r_batch, t_batch, s2_batch = rb_train.sample_batch(rb_train.replay_buffer_count)
                train_td_error = calc_td_error(sess, critic, config, s_batch, a_batch, r_batch, t_batch, s2_batch, rb_train.replay_buffer_count)

                s_batch, a_batch, r_batch, t_batch, s2_batch = rb_test.sample_batch(rb_test.replay_buffer_count)
                test_td_error = calc_td_error(sess, critic, config, s_batch, a_batch, r_batch, t_batch, s2_batch, rb_test.replay_buffer_count)

                print(td_error, mb_td_error, train_td_error, test_td_error)
                x.append(i)
                td_error_.append(td_error)
                mb_td_error_.append(mb_td_error)
                train_td_error_.append(train_td_error)
                test_td_error_.append(test_td_error)

                plt.plot(x, td_error_, 'r')
                plt.plot(x, mb_td_error_, 'g')
                plt.plot(x, train_td_error_, 'b')
                plt.plot(x, test_td_error_, 'k')
                plt.pause(0.05)

                if i%5000 == 0:
                    critic.save(sess, 'cl_network', global_step=i)

    plt.show(block=True)



def calc_td_error(sess, critic, config, s_batch, a_batch, r_batch, t_batch, s2_batch, size):
    # Calculate targets
    qq_val = []
    for stage in range(0,3):
        a_max = (stage-1)*np.ones((size,1))
        qq_val.append(critic.predict_(sess, s2_batch, action=a_max))
    q_val = np.concatenate(qq_val, axis=1)
    q_max = np.max(q_val, axis=1)

    y_i = []
    for k in range(size):
        if t_batch[k]:
            y_i.append(r_batch[k])
        else:
            y_i.append(r_batch[k] + config["gamma"] * q_max[k]) # target_q: list -> float

    q_i = critic.predict_(sess, s_batch, action=a_batch)
    td_error = np.sum(np.abs(q_i-np.reshape(y_i,newshape=(size,1))))
    td_error = td_error / size
    return td_error

######################################################################################
if __name__ == "__main__":
    main()
