from __future__ import print_function
import os
import argparse
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision
import torch.optim as optim
from torchvision import datasets, transforms

from TinyImageNet import TinyImageNet

import torchvision.models as models

import math

from autoattack_modified.autoattack import AutoAttack

from models import nets
from D2R import D2R_loss



### SEED
SEED=2022
torch.manual_seed(SEED)
torch.cuda.manual_seed(SEED)
np.random.seed(SEED)
torch.backends.cudnn.deterministic=True
####

parser = argparse.ArgumentParser(description='PyTorch CIFAR TRADES Adversarial Training')
parser.add_argument('--batch-size', type=int, default=128, metavar='N',
                    help='input batch size for training (default: 128)')
parser.add_argument('--test-batch-size', type=int, default=32, metavar='N',
                    help='input batch size for testing (default: 128)')
parser.add_argument('--epochs', type=int, default=100, metavar='N',
                    help='number of epochs to train')
parser.add_argument('--weight-decay', '--wd', default=2e-4,
                    type=float, metavar='W')
parser.add_argument('--lr', type=float, default=0.1, metavar='LR',
                    help='learning rate')
parser.add_argument('--momentum', type=float, default=0.9, metavar='M',
                    help='SGD momentum')
parser.add_argument('--no-cuda', action='store_true', default=False,
                    help='disables CUDA training')
parser.add_argument('--epsilon', default=0.031,
                    help='perturbation')
parser.add_argument('--num-steps', default=10,
                    help='perturb number of steps')
parser.add_argument('--step-size', default=0.007,
                    help='perturb step size')
parser.add_argument('--beta', default=6, type=float,
                    help='regularization, i.e., 1/lambda in TRADES')
parser.add_argument('--seed', type=int, default=1, metavar='S',
                    help='random seed (default: 1)')
parser.add_argument('--log-interval', type=int, default=100, metavar='N',
                    help='how many batches to wait before logging training status')
parser.add_argument('--model-dir', default='./model-cifar-10-inner-20-15-15adv',
                    help='directory of model for saving checkpoint')
parser.add_argument('--save-freq', '-s', default=1, type=int, metavar='N',
                    help='save frequency')
parser.add_argument('--save_path', type=str, default='', help='Path to save the trained model')

parser.add_argument('-teacher_model', type=str)

parser.add_argument('-teacher', type=str)
parser.add_argument('-mark', type=str)
parser.add_argument('-num_classes', type=int,default=10)

parser.add_argument('--lr-warmup', default=0, type=int,
                    help='warmup learning rate')
parser.add_argument('--awp-gamma', default=0.005, type=float,
                    help='whether or not to add parametric noise')

args = parser.parse_args()

# settings
model_dir = args.model_dir
if not os.path.exists(model_dir):
    os.makedirs(model_dir)
use_cuda = not args.no_cuda and torch.cuda.is_available()
torch.manual_seed(args.seed)
device = torch.device("cuda" if use_cuda else "cpu")
kwargs = {'num_workers': 1, 'pin_memory': True} if use_cuda else {}

# setup data loader
transform_train = transforms.Compose([
    transforms.RandomCrop(32, padding=4),
    transforms.RandomHorizontalFlip(),
    transforms.ToTensor(),
])
transform_test = transforms.Compose([
    transforms.ToTensor(),
])

#
trainset = torchvision.datasets.CIFAR10(root='./data/cifar10', train=True, download=True, transform=transform_train)
train_loader = torch.utils.data.DataLoader(trainset, batch_size=args.batch_size, shuffle=True, **kwargs)
testset = torchvision.datasets.CIFAR10(root='./data/cifar10', train=False, download=True, transform=transform_test)
test_loader = torch.utils.data.DataLoader(testset, batch_size=args.test_batch_size, shuffle=False, **kwargs)

#

# trainset = TinyImageNet(root='./tiny-imagenet-200', split='train', transform=transform_train, in_memory=True)
# trainloader = torch.utils.data.DataLoader(trainset, batch_size=64, shuffle=True, num_workers=2)
#
# testset = TinyImageNet(root='./tiny-imagenet-200', split='val', transform=transform_test, in_memory=True)
# testloader = torch.utils.data.DataLoader(testset, batch_size=64, shuffle=False, num_workers=2)

#
# trainset = torchvision.datasets.CIFAR100(root='./data/cifar100', train=True, download=True, transform=transform_train)
# train_loader = torch.utils.data.DataLoader(trainset, batch_size=args.batch_size, shuffle=True, **kwargs)
# testset = torchvision.datasets.CIFAR100(root='./data/cifar100', train=False, download=True, transform=transform_test)
# test_loader = torch.utils.data.DataLoader(testset, batch_size=args.test_batch_size, shuffle=False, **kwargs)




def train(args, model, model_teacher, device, train_loader, optimizer, epoch):
    model.train()
    for batch_idx, (data, target) in enumerate(train_loader):
        data, target = data.to(device), target.to(device)

        optimizer.zero_grad()

        # calculate robust loss
        loss = D2R_loss(model=model, model_teacher=model_teacher,
                           x_natural=data,
                           y=target,
                           optimizer=optimizer,
                           step_size=args.step_size,
                           epsilon=args.epsilon,
                           perturb_steps=args.num_steps,
                           beta=args.beta)
        loss.backward()
        optimizer.step()

        # print progress
        if batch_idx % args.log_interval == 0:
            open("Logs/"+args.mark,"a+").write('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}\n'.format(
                epoch, batch_idx * len(data), len(train_loader.dataset),
                       100. * batch_idx / len(train_loader), loss.item()))


def eval_train(model, device, train_loader):
    model.eval()
    train_loss = 0
    correct = 0
    with torch.no_grad():
        for data, target in train_loader:
            data, target = data.to(device), target.to(device)
            output = model(data)
            train_loss += F.cross_entropy(output, target, size_average=False).item()
            pred = output.max(1, keepdim=True)[1]
            correct += pred.eq(target.view_as(pred)).sum().item()
    train_loss /= len(train_loader.dataset)
    open("Logs/"+args.mark,"a+").write('Training: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(
        train_loss, correct, len(train_loader.dataset),
        100. * correct / len(train_loader.dataset)))
    training_accuracy = correct / len(train_loader.dataset)
    return train_loss, training_accuracy


def eval_test(model, device, test_loader):
    model.eval()
    test_loss = 0
    correct = 0
    with torch.no_grad():
        for data, target in test_loader:
            data, target = data.to(device), target.to(device)
            output = model(data)
            test_loss += F.cross_entropy(output, target, size_average=False).item()
            pred = output.max(1, keepdim=True)[1]
            correct += pred.eq(target.view_as(pred)).sum().item()
    test_loss /= len(test_loader.dataset)
    open("Logs/"+args.mark,"a+").write('Test: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(
        test_loss, correct, len(test_loader.dataset),
        100. * correct / len(test_loader.dataset)))
    test_accuracy = correct / len(test_loader.dataset)
    return test_loss, test_accuracy



def adjust_learning_rate(optimizer, epoch):
    """decrease the learning rate"""
    lr = args.lr
    if epoch==1:
       lr=0.02
    if epoch >= 76:
        lr = args.lr * 0.1
    if epoch >= 91:
        lr = args.lr * 0.01
    if epoch >= 101:
        lr = args.lr * 0.001
    for param_group in optimizer.param_groups:
        param_group['lr'] = lr

def adjust_learning_rate_cosine(optimizer, epoch):
    lr = args.lr
    if epoch < args.lr_warmup:
       lr = args.lr / args.lr_warmup * epoch
    else:
        lr *= 0.5 * (1. + math.cos(math.pi * (epoch - args.lr_warmup) / (args.epochs - args.lr_warmup + 1)))
    for param_group in optimizer.param_groups:
        param_group['lr'] = lr
    # return lr

def evaluate_standard(test_loader, model):
    test_loss = 0
    test_acc = 0
    n = 0
    model.eval()
    with torch.no_grad():
        for i, (X, y) in enumerate(test_loader):
            X, y = X.cuda(), y.cuda()
            output = model(X)
            loss = F.cross_entropy(output, y)
            test_loss += loss.item() * y.size(0)
            test_acc += (output.max(1)[1] == y).sum().item()
            n += y.size(0)
    return test_loss / n, test_acc / n



#
#     return model
def load_model_states(model, save_path, tag):
    """Load a previously saved model states."""
    filename = os.path.join(save_path, tag)
    with open(filename, 'rb') as f:
        state_dict = torch.load(f)

        from collections import OrderedDict
        new_state_dict = OrderedDict()
        for k, v in state_dict.items():
            name = k[7:] if k.startswith('module.') else k  # remove `module.`
            new_state_dict[name] = v
        model.load_state_dict(new_state_dict)


def main():
    # init model, ResNet18() can be also used here for training
    model = getattr(nets,"WideResNet")(num_classes=args.num_classes, widen_factor=10)

    # model = getattr(nets,args.teacher_model)(num_classes=args.num_classes)
    model_teacher = getattr(nets,args.teacher_model)(num_classes=args.num_classes)

    model = nn.DataParallel(model).to(device)
    model_teacher = nn.DataParallel(model_teacher).to(device)



    # optimizer
    optimizer = optim.SGD([{'params':model.parameters()},{'params':model_teacher.parameters()}], lr=args.lr, momentum=args.momentum, weight_decay=args.weight_decay)

    for epoch in range(1, args.epochs + 1):
        # adjust learning rate for SGD
        adjust_learning_rate(optimizer, epoch)

        train(args, model, model_teacher, device, train_loader, optimizer, epoch)

        # evaluation on natural examples
        open("Logs/"+args.mark,"a+").write('================================================================\n')
        eval_train(model, device, train_loader)
        eval_test(model, device, test_loader)
        open("Logs/"+args.mark,"a+").write('================================================================\n')

        # save checkpoint
        # if(epoch > 91 and epoch < 120)or (epoch % 10 == 0):
        # #
        if (epoch > 91 and epoch < 120) :
            torch.save(model.state_dict(),
                       os.path.join(model_dir, '{}-epoch{}.pt'.format(args.mark, epoch)))
            # torch.save(model_teacher.state_dict(),
            #            os.path.join(model_dir, '{}-natural-epoch{}.pt'.format(args.mark, epoch)))

        # if epoch % 20 == 0:
        #     torch.save(model_teacher.state_dict(),
        #                os.path.join(model_dir, '{}-natural-epoch{}.pt'.format(args.mark, epoch)))




if __name__ == '__main__':
    main()
