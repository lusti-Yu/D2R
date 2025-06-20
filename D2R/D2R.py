import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable


def squared_l2_norm(x):
    flattened = x.view(x.unsqueeze(0).shape[0], -1)
    return (flattened ** 2).sum(1)


def l2_norm(x):
    return squared_l2_norm(x).sqrt()


def D2R_loss(model, model_teacher,
                x_natural,
                y,
                optimizer,
                step_size=0.003,
                epsilon=0.031,
                perturb_steps=10,
                beta=1.0,
                distance='l_inf'):
    # define KL-loss
    # criterion_kl = nn.KLDivLoss(size_average=False)
    def criterion_kl(a, b):
        loss = -a * b + torch.log(b + 1e-5) * b
        return loss
    mse=torch.nn.MSELoss()
    ce=torch.nn.CrossEntropyLoss()
    softmax=torch.nn.Softmax(dim=1)

    model.eval()
    model_teacher.eval()
    batch_size = len(x_natural)
    # generate adversarial example
    x_adv = x_natural.detach() + 0.001 * torch.randn(x_natural.shape).cuda().detach()
    if distance == 'l_inf':
        for _ in range(perturb_steps):
            x_adv.requires_grad_()
            with torch.enable_grad():
                loss_kl = criterion_kl(F.log_softmax(model(x_adv), dim=1),
                                       F.softmax(model_teacher(x_natural), dim=1))
                loss_kl = torch.sum(loss_kl)
            grad = torch.autograd.grad(loss_kl, [x_adv])[0]
            x_adv = x_adv.detach() + step_size * torch.sign(grad.detach())
            x_adv = torch.min(torch.max(x_adv, x_natural - epsilon), x_natural + epsilon)
            x_adv = torch.clamp(x_adv, 0.0, 1.0)
    elif distance == 'l_2':
        for _ in range(perturb_steps):
            x_adv.requires_grad_()
            with torch.enable_grad():
                loss_kl = criterion_kl(F.log_softmax(model(x_adv), dim=1),
                                       F.softmax(model(x_natural), dim=1))
            grad = torch.autograd.grad(loss_kl, [x_adv])[0]
            for idx_batch in range(batch_size):
                grad_idx = grad[idx_batch]
                grad_idx_norm = l2_norm(grad_idx)
                grad_idx /= (grad_idx_norm + 1e-8)
                x_adv[idx_batch] = x_adv[idx_batch].detach() + step_size * grad_idx
                eta_x_adv = x_adv[idx_batch] - x_natural[idx_batch]
                norm_eta = l2_norm(eta_x_adv)
                if norm_eta > epsilon:
                    eta_x_adv = eta_x_adv * epsilon / l2_norm(eta_x_adv)
                x_adv[idx_batch] = x_natural[idx_batch] + eta_x_adv
            x_adv = torch.clamp(x_adv, 0.0, 1.0)
    else:
        x_adv = torch.clamp(x_adv, 0.0, 1.0)
    model.train()
    model_teacher.train()
    # model_teacher.eval()
    x_adv = Variable(torch.clamp(x_adv, 0.0, 1.0), requires_grad=False)
    # zero gradient
    optimizer.zero_grad()
    # calculate robust loss
    out_adv=model(x_adv)
    out_natural=model(x_natural)
    out=model_teacher(x_natural)

    def kl_loss(a, b):
        loss = -a * b + torch.log(b + 1e-5) * b
        return loss


    kl_Loss1 = kl_loss(F.log_softmax(out, dim=1),
                       F.softmax(out_natural, dim=1))
    kl_Loss2 = kl_loss(F.log_softmax(out_natural, dim=1),
                       F.softmax(out, dim=1))

    kl_Loss1 = torch.mean(kl_Loss1)
    kl_Loss2 = torch.mean(kl_Loss2)

    loss_klloss = torch.abs(kl_Loss1 - kl_Loss2)

    kl_Loss5 = kl_loss(F.log_softmax(out, dim=1),
                       F.softmax(out_adv, dim=1))
    kl_Loss3 = kl_loss(F.log_softmax(out_adv, dim=1),
                       F.softmax(out, dim=1))

    kl_Loss5 = torch.mean(kl_Loss5)
    kl_Loss3 = torch.mean(kl_Loss3)

    loss_kladvloss = torch.abs(kl_Loss2 - kl_Loss3)

    # #
    # loss_mse = ce(out, y) + mse(out_adv, out) + 30*kl_Loss5

    loss= ce(out, y) + mse(out_adv, out) + 20* loss_klloss + 30*kl_Loss5




    # loss_mse = ce(out, y)
    # print('kl_Loss5',  kl_Loss5)
    # print('kl_Loss3', kl_Loss3)
    # print('mse', mse(out_adv, out))
    # print('mse', loss_mse )
    # #
    # print('ce', ce(out,y))


    return loss
