import torch
import albumentations as A
from albumentations.pytorch import ToTensorV2
from tqdm import tqdm
import torch.nn as nn
import torch.optim as optim
from model import UNET

# hyperparameters
LEARNING_RATE = 1e-4
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'
BATCH_SIZE = 20
NUM_EPOCHS = 5
IMAGE_HEIGHT = 160
IMAGE_WIDTH  = 240
TRAIN_IMG_DIR = "C:/Users/USER/Desktop/Carvana/train/"
TRAIN_MASK_DIR = "C:/Users/USER/Desktop/Carvana/train_mask/"
VAL_IMG_DIR = "C:/Users/USER/Desktop/Carvana/val/"
VAL_MASK_DIR = "C:/Users/USER/Desktop/Carvana/val_mask/"

def train_fn(loader, model, optimizer, loss_fn, scaler):
    loop = tqdm(loader)

    for batch_idx, (data, targets) in enumerate(loop):
        data = data.to(device = DEVICE)
        targets = targets.float().unsqueeze(1).to(device = DEVICE)

        # forward
        with torch.cuda.amp.autocast():
            prediction = model(data)
            loss = loss_fn(prediction, targets)

        # backward
        optimizer.zero_grad()
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()

        # Update tqdm loop
        loop.set_postfix(loss = loss.item())


def main():
    train_transform = A.Compose([
        A.Resize(height = IMAGE_HEIGHT, width = IMAGE_WIDTH),
        A.Rotate(limit=35, p =1.0),
        A.HorizontalFlip(p = 0.5),
        A.VerticalFlip(p = 0.1),
        A.Normalize(
            mean = [0.0, 0.0, 0.0],
            std  = [1.0, 1.0, 1.0],
            max_pixel_value = 255.0
        ),
        ToTensorV2()
    ])

    val_transform = A.Compose([
        A.Resize(height=IMAGE_HEIGHT, width=IMAGE_WIDTH),
        A.Normalize(
            mean=[0.0, 0.0, 0.0],
            std=[1.0, 1.0, 1.0],
            max_pixel_value=255.0
        ),
        ToTensorV2()
    ])

    model = UNET(in_channels = 3, out_channels = 1).to(device = DEVICE)
    loss_fn = nn.BCEWithLogitsLoss()

    # for mutliclass ...
    # model = UNET(in_channels=3, out_channels= 2 ~).to(device=DEVICE)
    # loss_fn = cross entropy loss ...

    optimizer = optim.Adam(model.paramters(), lr = LEARNING_RATE)
    train_loader, val_loader = get_loaders(
        TRAIN_IMG_DIR,
        TRAIN_MASK_DIR,
        VAL_IMG_DIR,
        VAL_MASK_DIR,
        BATCH_SIZE,
        train_transform,
        val_transform,

        NUM_WORKERS,
        PIN_MEMORY
    )

    scaler = torch.cuda.amp.GradScaler()
    for epoch in range(NUM_EPOCHS):
        train_fn(train_loader, model, optimizer, loss_fn, scaler)

        # save model
        # check accuracy
        # print some examples to a folder



if __name__ == "__main__":
    main()