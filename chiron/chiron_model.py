# Copyright 2017 The Chiron Authors. All Rights Reserved.
#
#This Source Code Form is subject to the terms of the Mozilla Public
#License, v. 2.0. If a copy of the MPL was not distributed with this
#file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
#Created on Mon Mar 17 20:56:18 2018
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
import tensorflow as tf
from cnn import getcnnfeature
from cnn import getcnnlogit
from rnn import rnn_layers

MOVING_AVERAGE_DECAY = 0.9999

def loss(logits, seq_len, label):
    """Calculate a CTC loss from the input logits and label.

    Args:
        logits: Tensor of shape [batch_size,max_time,class_num], logits from last layer of the NN, usually from a
            Fully connected layyer.
        seq_len: Tensor of shape [batch_size], sequence length for each sample in the batch.
        label: A Sparse Tensor of labels, sparse tensor of the true label.

    Returns:
        Tensor of shape [batch_size], losses of the batch.
    """
    loss = tf.reduce_mean(
        tf.nn.ctc_loss(label, logits, seq_len, ctc_merge_repeated=True,
                       time_major=False))
    tf.add_to_collection('losses',loss)
    """Note here ctc_loss will perform softmax, so no need to softmax the logits."""
    tf.summary.scalar('loss', loss)
    return tf.add_n(tf.get_collection('losses'),name = 'total_loss')


def train_opt(init_rate,max_steps,global_step=None, opt_name="Adam"):
    """Generate training op

    Args:
        init_rate: initial learning rate.
        max_steps: maximum training steps.
        global_step: A optional Scalar tensor, the global step recorded, if None no global stop will be recorded.
        opt_name: An optional string from : "Adam","SGD","RMSProp","Momentum". Defaults to "Adam". Specify the optimizer.
    Returns:
        opt: Optimizer
    """
    optimizers = {"Adam": tf.train.AdamOptimizer,
                  "SGD": tf.train.GradientDescentOptimizer,
                  "RMSProp": tf.train.RMSPropOptimizer,
                  "Momentum": tf.train.MomentumOptimizer}
    boundaries = [int(max_steps*0.66), int(max_steps*0.83)]
    values = [init_rate * decay for decay in [1,1e-1,1e-2]]
    learning_rate = tf.train.piecewise_constant(global_step,boundaries,values)
    opt = optimizers[opt_name](learning_rate)
    return opt

def prediction(logits, seq_length, label,beam_width = 30, top_paths=1):
    """
    Args:
        logits:Input logits from a RNN.Shape = [batch_size,max_time,class_num]
        seq_length:sequence length of logits. Shape = [batch_size]
        label:Sparse tensor of label.
        beam_width(Int):Beam width used in beam search decoder.
        top_paths:The number of top score path to choice from the decorder.
    """
    logits = tf.transpose(logits, perm=[1, 0, 2])
    if beam_width == 0:
        predict = tf.nn.ctc_greedy_decoder(
                                        logits, 
                                        seq_length, 
                                        merge_repeated=True,
                                        top_paths = top_paths)
    else:
        predict = tf.nn.ctc_beam_search_decoder(
                                        logits, 
                                        seq_length, 
                                        merge_repeated=False,
                                        top_paths=top_paths,
                                        beam_width=beam_width)
    predict = predict[0]
    edit_d = list()
    for i in range(top_paths):
        tmp_d = tf.edit_distance(tf.to_int32(predict[i]), label, normalize=True)
        edit_d.append(tmp_d)
    tf.stack(edit_d, axis=0)
    d_min = tf.reduce_min(edit_d, axis=0)
    error = tf.reduce_mean(d_min, axis=0)
    tf.summary.scalar('Error_rate', error)
    return error

def inference(x,sequence_len,training,full_sequence_len,rnn_layer_num = 3):
    """Infer a logits of the input signal batch.

    Args:
        x: Tensor of shape [batch_size, max_time,channel], a batch of the input signal with a maximum length `max_time`.
        sequence_len: Tensor of shape [batch_size], given the real lenghs of the segments.
        training: Placeholder of Boolean, Ture if the inference is during training.
        full_sequence_len: Scalar float, the maximum length of the sample in the batch.
        rnn_layer_num:Scalar Int, default is 3, the number of layer of RNN in the network.

    Returns:
        logits: Tensor of shape [batch_size, max_time, class_num]
        ratio: Scalar float, the scale factor between the output logits and the input maximum length.
    """
    cnn_feature = getcnnfeature(x,training = training)
    feashape = cnn_feature.get_shape().as_list()
    ratio = full_sequence_len/feashape[1]
    if rnn_layer_num == 0:
        logits = getcnnlogit(cnn_feature)
    else:
        logits = rnn_layers(cnn_feature,sequence_len,training,layer_num = rnn_layer_num)
        #logits = cudnn_rnn(cnn_feature,rnn_layer_num)
    return logits,ratio