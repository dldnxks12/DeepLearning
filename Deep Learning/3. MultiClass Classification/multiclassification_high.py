# api 사용해서 softmax regression (multi class classfication 구현)

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import numpy as np
x_train = [[1, 2, 1, 1],
           [2, 1, 3, 2],
           [3, 1, 3, 4],
           [4, 1, 5, 5],
           [1, 7, 5, 5],
           [1, 2, 5, 6],
           [1, 6, 6, 6],
           [1, 7, 7, 7]]
y_train = [2, 2, 2, 1, 1, 1, 0, 0]

x_train = torch.FloatTensor(x_train) # size = (8, 4)
y_train = torch.LongTensor(y_train)  # size = (8,  )

# F.cross_entropy 사용할 것이기에 y_train data encoding 불필요 (F.cross_entropy = F.log_softmax + F.nll_loss)
W = torch.zeros((4,3), requires_grad=True)
b = torch.zeros(1, requires_grad=True)

optimizer = optim.SGD([W,b], lr = 0.1)
num_epochs = 1000

for epoch in range(num_epochs+1):
    
    z = x_train.matmul(W) + b
    cost = F.cross_entropy(z, y_train)
    
    optimizer.zero_grad()
    cost.backward()
    optimizer.step()

    if epoch % 100 == 0:
        print('Epoch {:4d}/{} Cost: {:.6f}'.format(
            epoch, num_epochs, cost.item()
        ))
