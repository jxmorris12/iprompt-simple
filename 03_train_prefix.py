from typing import Dict, List
import datasets
import os
import random
import string
import numpy as np
import torch
from torch import nn
import transformers
import matplotlib.pyplot as plt
import argparse
from transformers import pipeline
from transformers import AutoTokenizer, AutoModel, AutoModelForCausalLM
from copy import deepcopy
import pandas as pd
from tqdm import tqdm
from collections import defaultdict
from model_utils.prefix import (
    PrefixTunedModel, PromptTunedModel, HotFlipPrefixTunedModel, GumbelPrefixTunedModel
)
import pandas as pd
from datasets import Dataset
import data
import logging
import pickle as pkl
from torch.utils.data import DataLoader
from datetime import datetime


device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


model_cls_dict = {
    'gumbel': GumbelPrefixTunedModel,
    'hotflip': HotFlipPrefixTunedModel,
    'prompt_tune': PromptTunedModel,
}


def train(
        args: argparse.Namespace,
        r: Dict[str, List],
        dset: datasets.Dataset,
        model: PrefixTunedModel,
        tokenizer: transformers.PreTrainedTokenizer,
        gamma: float
    ):
    """
    Params
    ------
    r: dict
        dictionary of things to save
    """
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    model.train() 

    model = model.to(device)
    dataloader = DataLoader(dset, batch_size=args.batch_size, shuffle=True, drop_last=False)

    # set up saving
    save_dir_unique = datetime.now().strftime("%b_%d_%H_%M_") + ''.join(random.choices(string.ascii_lowercase, k=12))
    save_dir = os.path.join(args.save_dir, save_dir_unique)
    logging.info('saving to ' + save_dir)

    # optimizer
    optim = torch.optim.AdamW(model.trainable_params, lr=args.lr)

    assert model.training
    for epoch in range(args.n_epochs):
        model.pre_epoch()

        all_losses = []
        
        total_n = 0
        total_n_correct = 0
        pbar = tqdm(enumerate(dataloader), total=len(dataloader))
        for idx, batch in pbar:
            # todo; update template
            x_text = [prompt.replace('Given ', '') for prompt in batch['input']]
            y_text = [answer.replace('.', '').rstrip() for answer in batch['output']] # strip newlines and periods.
            full_text = [x_text[i] for i in range(len(x_text))]

            # calculate loss
            # currently this calculates loss only on the answer token
            idxs_correct = tokenizer(y_text, return_tensors='pt')['input_ids'].to(device)
            try:
                assert idxs_correct.nelement() == len(y_text), 'For now assume that each answer is a single token'
            except:
                print("error!")
                breakpoint()
            # (batch_size, seq_len, vocab_size)

            input_ids, outputs = model.forward_text(text=full_text)

            log_probs = outputs['logits'].log_softmax(dim=-1)

            last_token_logprobs = log_probs[:, -1, :]
            correct_token_logprobs = torch.gather(last_token_logprobs, 1, idxs_correct)

            total_n += len(last_token_logprobs)
            total_n_correct += (last_token_logprobs.argmax(dim=-1) == idxs_correct.flatten()).int().sum()

            lm_loss = 0.0
            if gamma > 0:
                # Compute fluency loss.
                # TODO handle masking correctly.
                num_input_words = input_ids.shape[1]
                log_probs_for_input = log_probs[:, -1-num_input_words:-1, :]
                input_log_probs = torch.gather(
                    log_probs_for_input, dim=2, index=input_ids[...,None].to(device)
                )
                lm_loss = input_log_probs.mean()

            # accumulate gradients in this batch
            loss = -1 * (correct_token_logprobs.mean() + lm_loss * gamma) # minimize prob answer being wrong
            all_losses.extend((-1 * correct_token_logprobs).flatten().tolist())
            loss.backward()
            pbar.set_description(f"Loss = {loss:.3f}")

            # optimize
            # optim.step()
            # optim.zero_grad()

        
        avg_loss = sum(all_losses) / len(all_losses)
        print(f"Epoch {epoch}. average loss = {avg_loss:.3f} / {total_n_correct} / {total_n} correct ({total_n_correct/total_n*100:.2f}%)")

        # save stuff
        for key, val in model.compute_metrics().items():
            r[key].append(val)

        r['losses'].append(avg_loss)
        if epoch % args.epoch_save_interval == 0:
            os.makedirs(save_dir, exist_ok=True)
            pkl.dump(r, open(os.path.join(save_dir, 'results.pkl'), 'wb'))

        model.post_epoch()

        # optimize
        optim.step()
        optim.zero_grad()


    return r


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('--model_cls', type=str,
                    choices=model_cls_dict.keys(),
                    required=True,
                    help='model type to use for training')
    parser.add_argument('--batch_size', type=int, default=500,
                        help='batch size for training')
    parser.add_argument('--max_dset_size', type=int,
                        default=10000, help='maximum allowable dataset size')
    parser.add_argument('--template_num_task_phrasing', type=int, default=0,
                        help='the number of the manual template for any given task (number of options varies with task')
    parser.add_argument('--seed', type=int, default=1,
                        help='random seed')
    parser.add_argument('--n_epochs', type=int, default=10000,
                        help='number of epochs for training')
    parser.add_argument('--max_digit', type=int, default=100,
                        help='maximum value of each digit in summand')
    parser.add_argument('--save_dir', type=str, default='results',
                        help='directory for saving')
    parser.add_argument('--epoch_save_interval', type=int, default=1,
                        help='interval to save results')
    parser.add_argument('--lr', type=float, default=1e-4,
                        help='learning rate')
    parser.add_argument('--gamma', type=float, default=0.0,
                        help='hparam: weight for language modeling loss')
    parser.add_argument('--checkpoint', type=str, default="EleutherAI/gpt-neo-2.7B",
                        choices=(
                            "EleutherAI/gpt-neo-125M",
                            "EleutherAI/gpt-neo-1.3B",
                            "EleutherAI/gpt-neo-2.7B",
                            "gpt2",        # 117M params
                            "gpt2-medium", # 355M params
                            "gpt2-large",  # 774M params
                            "gpt2-xl",     # 1.5B params
                        ),
                        help='model checkpoint to use')
    args = parser.parse_args()
    r = defaultdict(list)
    r.update(vars(args))
    logger = logging.getLogger()
    logging.basicConfig(level=logging.INFO)

    logger.info('loading model and data...')
    checkpoint = args.checkpoint
    tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    lm = AutoModelForCausalLM.from_pretrained(
        checkpoint, output_hidden_states=True)
    model = model_cls_dict[args.model_cls](model=lm, tokenizer=tokenizer)
    dset, check_answer_func, description = data.get_data(args=args, task_name='add_two')
    print(f"got task with description: {description}")

    logger.info('beginning training...')
    r = train(args=args, r=r, dset=dset, model=model, tokenizer=tokenizer, gamma=args.gamma)
