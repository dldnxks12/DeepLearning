'''
# Info
# 이산화 ing
# Optimize Part Error : RuntimeError: grad can be implicitly created only for scalar outputs
'''
import gym
import sys
import copy
import random
import numpy as np
import matplotlib.pyplot as plt

import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F

from torch.distributions import Categorical
from time import sleep
from collections import deque

device = 'cuda' if torch.cuda.is_available() else 'cpu'
print("")
print(f"On {device}")
print("")

## Hyper-Parameters
lr       = 0.0005 # Learning Rate
gamma    = 0.98   # Discount Factor
LD       = 0.95   # GAE
Eps_clip = 0.1    # L_Clip 범위
K        = 3      # 모아둔 데이터 반복 학습 횟수
T        = 200    # 데이터 모을 Time Step

class PPO(nn.Module):
    def __init__(self, DiscretizedActionRange):
        super(PPO, self).__init__()

        self.fc1 = nn.Linear(3, 256)  # SIN , COS, Angular Vel
        self.fc2 = nn.Linear(256, 256)

        self.fc_pi_a11 = nn.Linear(256, 128)
        self.fc_pi_a12 = nn.Linear(128, DiscretizedActionRange)

        self.fc_v = nn.Linear(256, 1)

    def PI(self, x, softmax_dim=0):
        print(x.shape)
        print("OKOK")
        x1 = F.relu(self.fc1(x))
        x1 = self.fc_pi_a11(x1)
        x1 = self.fc_pi_a12(x1)
        x1 = torch.tanh(x1)
        prob_a1 = F.softmax(x1, dim=softmax_dim)

        return [x1, prob_a1]

    def v(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        v = self.fc_v(x)
        return v


def make_batch():
    states, actions, action_idx, rewards, next_states, probs, dones = [], [], [], [], [], [], []

    for transition in data:
        state, action, action_index, reward, next_state, prob, done = transition
        states.append(state)
        actions.append(action)
        action_idx.append(action_index)
        rewards.append(torch.tensor(reward))
        next_states.append(next_state)
        probs.append(prob)
        done_mask = 0 if done else 1
        dones.append(done_mask)

    states = torch.tensor(states, dtype=torch.float)
    actions = torch.tensor(actions)
    action_idx = torch.tensor(action_idx)
    rewards = torch.tensor(rewards, dtype=torch.float)
    next_states = torch.tensor(next_states, dtype=torch.float)
    dones = torch.tensor(dones)
    probs = torch.tensor(probs, dtype=torch.float)

    return states, actions, action_idx, rewards, next_states, dones, probs


def train(ppo, optimizer):
    states, actions, action_idx, rewards, next_states, dones, probs = make_batch()
    for i in range(K):  # 같은 배치 데이터에 대해 K번 학습
        TD_Target = rewards + gamma * ppo.v(next_states) * dones
        Delta = TD_Target - ppo.v(states)
        Delta = Delta.detach().numpy()

        GAE_list = []
        GAE = 0.0
        for Delta_t in Delta[::-1]:
            GAE = gamma * LD * GAE + Delta_t[0]
            GAE_list.append([GAE])
        GAE_list.reverse()

        GAE_Value = torch.tensor(GAE_list, dtype=torch.float)

        old_a1, old_a2, old_a3, old_a4 = ppo.PI(states, softmax_dim=1)

        # Softmax 분포만 가져오기
        _, a1_prob = old_a1

        probs_old = a1_prob.gather(1, action_idx)
        #probs_old_1 = a1_prob.gather(1, action_idx.unsqueeze(0))


        #probs_old = torch.stack([probs_old_1, probs_old_2, probs_old_3, probs_old_4], axis=1).transpose(0, 2)
        Ratio = torch.exp(torch.log(probs_old) - torch.log(probs))

        print(Ratio.shape)
        print("OK")

        sys.exit()

        ######################################### ? ####################################################
        ######################################## Error #################################################

        '''

        # Ratio shape : Batch Size x 4

        Surrogate11 = Ratio[:,0].unsqueeze(1) * GAE_Value
        Surrogate12 = Ratio[:,1].unsqueeze(1) * GAE_Value
        Surrogate13 = Ratio[:,2].unsqueeze(1) * GAE_Value
        Surrogate14 = Ratio[:,3].unsqueeze(1) * GAE_Value
        Surrogate21 = torch.clamp(Ratio[:,0].unsqueeze(1), 1 - Eps_clip, 1 + Eps_clip) * GAE_Value
        Surrogate22 = torch.clamp(Ratio[:,1].unsqueeze(1), 1 - Eps_clip, 1 + Eps_clip) * GAE_Value
        Surrogate23 = torch.clamp(Ratio[:,2].unsqueeze(1), 1 - Eps_clip, 1 + Eps_clip) * GAE_Value
        Surrogate24 = torch.clamp(Ratio[:,3].unsqueeze(1), 1 - Eps_clip, 1 + Eps_clip) * GAE_Value

        # -torch.min(~) : 문제 있음 # RuntimeError: grad can be implicitly created only for scalar outputs
        # F.smooth_l1_loss( ~ ) : 문제 없음

        loss = ((- torch.min(Surrogate11, Surrogate21) - torch.min(Surrogate12, Surrogate22)  \
                 - torch.min(Surrogate13, Surrogate23) - torch.min(Surrogate14, Surrogate24)) \
                 + F.smooth_l1_loss(ppo.v(states) , TD_Target.detach()))
        '''

        ######################################## Error #################################################

        # Continuous Action Space Method (Original Baseline Method)
        Surrogate1 = Ratio * GAE_Value
        Surrogate2 = torch.clamp(Ratio, 1 - Eps_clip, 1 + Eps_clip) * GAE_Value

        loss = -torch.min(Surrogate1, Surrogate2) + F.smooth_l1_loss(ppo.v(states), TD_Target.detach())

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        print("OK")
        sys.exit()


def Discretization(a1):
    actions1, prob_a1 = a1

    # SoftMax 분포에 따라 Action Sample (Return Index)
    action_index1 = Categorical(prob_a1).sample().item()


    # Continuous Action
    action1 = actions1[action_index1].cpu().detach().numpy()


    # Discretize (Return Index)
    discrete_action1 = np.array([np.digitize(action1, bins=A)])


    # Discretized Action
    discrete_action1 = A[discrete_action1]


    # Probabilities of Above Actions
    action1_prob = np.array([prob_a1[action_index1].cpu().detach().numpy()])


    action = [discrete_action1]
    action_prob = [action1_prob]
    action_index = [action_index1]
    return action, action_prob, action_index


env = gym.make('Pendulum-v1')
A = np.arange(-1, 1, 0.005)  # Discrete Action Range
ppo = PPO(DiscretizedActionRange=len(A)).to(device)
optimizer = optim.Adam(ppo.parameters(), lr=lr)

score = 0.0
episode = 0
MAX_EPISODES = 3000
reward_history_10 = []
avg_history = []

while episode < MAX_EPISODES:
    state = env.reset()
    done = False
    data = []
    while not done:
        # T Step 동안 데이터 수집
        for t in range(T):
            a1= ppo.PI(torch.from_numpy(state).float().to(device))
            action, action_prob, action_index= Discretization(a1)
            next_state, reward, done, _ = env.step(action)
            data.append((state, action, action_index,  reward, next_state, action_prob, done))

            state = next_state
            score += reward

            if done:
                break

        train(ppo, optimizer)
        data = []

    # Moving Average Count
    reward_history_10.append(score)
    avg = sum(reward_history_10[-10:]) / 10
    avg_history.append(avg)
    if episode % 10 == 0:
        print(f'episode: {episode} | reward: {score} | 10 avg: {avg} ')
    episode += 1

env.close()