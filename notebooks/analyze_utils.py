import numpy as np
import torch
from torch import nn
import matplotlib.pyplot as plt
from copy import deepcopy
import pandas as pd
from tqdm import tqdm
from collections import defaultdict
from transformers import AutoTokenizer
import pandas as pd
import seaborn as sns
from datasets import Dataset
from os.path import join as oj
import pickle as pkl
import os


def load_results_and_cache(results_dir, save_file='r.pkl'):
    dir_names = sorted([fname
                        for fname in os.listdir(results_dir)
                        if os.path.isdir(oj(results_dir, fname))
                        and os.path.exists(oj(results_dir, fname, 'results_final.pkl'))
                        ])
    results_list = []
    for dir_name in tqdm(dir_names):
        try:
            ser = pd.Series(
                pkl.load(open(oj(results_dir, dir_name, 'results_final.pkl'), "rb")))
            # only keep scalar-valued vars
            ser_scalar = ser[~ser.apply(
                lambda x: isinstance(x, list)).values.astype(bool)]
            results_list.append(ser_scalar)
        except:
            print('skipping', dir_name)

    r = pd.concat(results_list, axis=1).T.infer_objects()
    r.to_pickle(os.path.join(results_dir, save_file))
    return r


def postprocess_results(r):
    """
    # drop some things to make it easier to see
    cols = r.columns
    cols_to_drop = [k for k in cols
                    if k.endswith('prefix') or k.endswith('init') # or k.startswith('use')
                    ]
    cols_to_drop += ['epoch_save_interval', 'batch_size']
    r = r.drop(columns=cols_to_drop)
    """
    # print(r.keys())
    if 'final_answer_full' in r.columns:
        r['final_answer_found'] = (~r['final_answer_full'].isna()).astype(int)
    else:
        r['final_answer_found'] = 0

    """
    r['use_single_query'] = (
        r['use_single_query']
        .astype(bool)
        .map({True: 'Single-query',
              False: 'Avg suffix'})
    )
    """

    # add metrics
    metric_keys = []
    for i in [3, 5, 10, 15, 20, 25, 30, 40, 50, 75, 100, 150, 200]:
        metric_key = f'acc@{i}'
        r[metric_key] = (r['final_num_suffixes_checked'] <= i)
        metric_keys.append(metric_key)
    return r


def num_suffixes_checked_tab(tab, metric_key='final_num_suffixes_checked'):
    return (tab
            # mean over templates, task_name)
            .groupby(['checkpoint', 'n_shots'])[[metric_key, 'use_single_query']]
            .mean()
            .reset_index()
            )            

def plot_tab(tab, metric_key, title):
    # reformat legend
    VALS = {
        True: 'Single-query sample',
        False: 'Ours: Average suffix sampling',
    }
    tab['Legend'] = tab['use_single_query'].map(VALS) + ' (nshots=' + tab['n_shots'].astype(str) + ')'

    # make plot
    sns.barplot(x='checkpoint', y=metric_key, hue='Legend', data=tab) #data=tab[tab['n_shots'] == 1])
    plt.xlabel('Model name')
    YLABS = {
        'final_num_suffixes_checked': 'Number of suffixes checked before finding correct answer\n(lower is better)',
    }
    plt.ylabel(YLABS.get(metric_key, metric_key))
    plt.title(title, fontsize='medium')
    plt.tight_layout()
    plt.show()