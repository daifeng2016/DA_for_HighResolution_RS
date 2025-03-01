import torch
import torch.nn as nn
from torch.autograd import Variable as V

import cv2
import numpy as np
import torch.nn.functional as F
from losses.SSIM import SSIM


def N8ASCLoss(probs, size=1):
    _, _, h, w = probs.size()
    #softmax = F.softmax(probs, dim=1)
    p = size
    softmax_pad = F.pad(probs, [p]*4, mode='replicate')
    affinity_group = []
    for st_y in range(0, 2*size+1, size):  # 0, size, 2*size
        for st_x in range(0, 2*size+1, size):
            if st_y == size and st_x == size:#computing the 8 neighbours except (1,1)
                continue
            affinity_paired = torch.sum(
                softmax_pad[:, :, st_y:st_y+h, st_x:st_x+w] * probs, dim=1)
            affinity_group.append(affinity_paired.unsqueeze(1))
    affinity = torch.cat(affinity_group, dim=1)
    loss = 1.0 - affinity
    return loss.mean()

def N4ASCLoss(probs, size=1):
    _, _, h, w = probs.size()
    #softmax = F.softmax(probs, dim=1)#[2,3,128,128]
    p = size
    softmax_pad = F.pad(probs, [p]*4, mode='replicate')#[2,3,130,130]
    affinity_group = []
    for st_y in range(0, 2*size+1, size):  # 0, size, 2*size     range(start, stop[, step])
        for st_x in range(0, 2*size+1, size):#implement p_x * p_n in the four neighbourhood
            if abs(st_y-st_x) == size:#(0,1)(1,0) (1,2) (2,1)
                affinity_paired = torch.sum(
                    softmax_pad[:, :, st_y:st_y+h, st_x:st_x+w] * probs, dim=1)#[2,128,128]
                affinity_group.append(affinity_paired.unsqueeze(1))#[2,1,128,128]
    affinity = torch.cat(affinity_group, dim=1)#[2,4,128,128]
    loss = 1.0 - affinity#[2,4,128,128]
    return loss.mean()

def eightwayASCLoss(probs, size=1):
    _, _, h, w = probs.size()
    softmax = F.softmax(probs, dim=1)
    p = size
    softmax_pad = F.pad(softmax, [p]*4, mode='replicate')
    affinity_group = []
    for st_y in range(0, 2*size+1, size):  # 0, size, 2*size
        for st_x in range(0, 2*size+1, size):
            if st_y == size and st_x == size:#computing the 8 neighbours except (1,1)
                continue
            affinity_paired = torch.sum(
                softmax_pad[:, :, st_y:st_y+h, st_x:st_x+w] * softmax, dim=1)
            affinity_group.append(affinity_paired.unsqueeze(1))
    affinity = torch.cat(affinity_group, dim=1)
    loss = 1.0 - affinity
    return loss.mean()

def fourwayASCLoss(probs, size=1):
    _, _, h, w = probs.size()
    softmax = F.softmax(probs, dim=1)#[2,3,128,128]
    p = size
    softmax_pad = F.pad(softmax, [p]*4, mode='replicate')#[2,3,130,130]
    affinity_group = []
    for st_y in range(0, 2*size+1, size):  # 0, size, 2*size     range(start, stop[, step])
        for st_x in range(0, 2*size+1, size):#implement p_x * p_n in the four neighbourhood
            if abs(st_y-st_x) == size:#(0,1)(1,0) (1,2) (2,1)
                affinity_paired = torch.sum(
                    softmax_pad[:, :, st_y:st_y+h, st_x:st_x+w] * softmax, dim=1)#[2,128,128]
                affinity_group.append(affinity_paired.unsqueeze(1))#[2,1,128,128]
    affinity = torch.cat(affinity_group, dim=1)#[2,4,128,128]
    loss = 1.0 - affinity#[2,4,128,128]
    return loss.mean()








def soft_label_cross_entropy(pred, soft_label, pixel_weights=None):
    N, C, H, W = pred.shape
    loss = -soft_label.float()*F.log_softmax(pred, dim=1)
    if pixel_weights is None:
        return torch.mean(torch.sum(loss, dim=1))
    return torch.mean(pixel_weights*torch.sum(loss, dim=1))



class FocalLoss(nn.Module):
    def __init__(self, alpha=0.25, gamma=2, weight=None, ignore_index=None):
        super(FocalLoss, self).__init__()
        self.alpha = alpha
        self.gamma = gamma
        self.weight = weight
        self.ignore_index = ignore_index
        self.bce_fn = nn.BCELoss(weight=self.weight)

    def forward(self, preds, labels):
        if self.ignore_index is not None:
            mask = labels != self.ignore
            labels = labels[mask]
            preds = preds[mask]

        logpt = -self.bce_fn(preds, labels)
        pt = torch.exp(logpt)
        loss = -((1 - pt) ** self.gamma) * self.alpha * logpt
        return loss


#===========dice_loss+bce_loss==================
from models.layers.loss import CrossEntropy2d
class dice_bce_loss(nn.Module):
    def __init__(self, batch=True):
        super(dice_bce_loss, self).__init__()
        self.batch = batch
        self.bce_loss = nn.BCELoss()
        #self.bce_loss =CrossEntropy2d()
        self.weight=2.0

    def soft_dice_coeff(self, y_true, y_pred):
        smooth = 1.0  # may change
        if self.batch:
            i = torch.sum(y_true)#对二维或多维矩阵的所有元素求和
            j = self.weight*torch.sum(y_pred)
            intersection = torch.sum(y_true * y_pred)
        else:
            i = y_true.sum(1).sum(1).sum(1)#only for batch=1
            j = y_pred.sum(1).sum(1).sum(1)
            intersection = (y_true * y_pred).sum(1).sum(1).sum(1)
        score = (2. * intersection + smooth) / (i + j + smooth)
        # score = (intersection + smooth) / (i + j - intersection + smooth)#iou
        return score.mean()

    def soft_dice_loss(self, y_true, y_pred):
        loss = 1 - self.soft_dice_coeff(y_true, y_pred)
        return loss

    def __call__(self, y_pred, y_true):
        a = self.bce_loss(y_pred, y_true)
        b = self.soft_dice_loss(y_true, y_pred)
        return a + b
#====================for genearized dice loss========================
from models.utils import one_hot
from torch.autograd import Variable
class gen_dice_loss(nn.Module):
    def __init__(self, batch=True):
        super(gen_dice_loss, self).__init__()
        self.batch = batch
        #self.bce_loss = nn.BCELoss()
        self.bce_loss =CrossEntropy2d()
        self.weight=2.0

    def soft_dice_coeff(self, y_true, y_pred):
        smooth = 1.0  # may change
        # if self.batch:
        #     i = torch.sum(y_true)#对二维或多维矩阵的所有元素求和
        #     j = self.weight*torch.sum(y_pred)
        #     intersection = torch.sum(y_true * y_pred)
        # else:
        #     i = y_true.sum(1).sum(1).sum(1)#only for batch=1
        #     j = y_pred.sum(1).sum(1).sum(1)
        #     intersection = (y_true * y_pred).sum(1).sum(1).sum(1)
        # score = (2. * intersection + smooth) / (i + j + smooth)
        #target.transpose(1, 2).transpose(2, 3).contiguous().view(1, -1)
        if y_true.dim()!=4:
            y_pred = F.softmax(y_pred, dim=1)
            y_true = Variable(one_hot(y_true.data.cpu())).cuda()
        y_true=y_true.transpose(1, 2).transpose(2, 3).contiguous().view(-1, 2)
        y_pred = y_pred.transpose(1, 2).transpose(2, 3).contiguous().view(-1, 2)
        # y_true = y_true.view(-1, 2)  # [1,3,4,2]==>[12,2]
        # y_pred = y_pred.view(-1, 2)
        sum_p = y_pred.sum(0)  # [1,2]
        sum_r = y_true.sum(0)  # [1,2]
        sum_pr = (y_pred * y_true).sum(0)  # [1,2]
        weights=1.0-sum_r/sum_r.sum(0)
        #weights = torch.pow(sum_r ** 2 + 1e-6, -1)  # seem not useful, sum_r**2==pow(sum_r,2)
        # weights=1/(sum_r**2+1e-6)
        gene_dice = (2 * (weights * sum_pr).sum(0).sum(0)+smooth) / ((weights * (sum_r + sum_p)).sum(0).sum(0)+smooth)

        return gene_dice.mean()

    def soft_dice_loss(self, y_true, y_pred):
        loss = 1 - self.soft_dice_coeff(y_true, y_pred)
        return loss

    def __call__(self, y_pred, y_true):
        a = self.bce_loss(y_pred, y_true)
        b = self.soft_dice_loss(y_true, y_pred)
        return a+0.05*b
#====================for weighted binary cross_entropy loss================
class weighted_ce_loss(nn.Module):
    def __init__(self, batch=True):
        super(weighted_ce_loss, self).__init__()


    def my_ce_loss(self, y_pred, y_true):
        smooth = 1.0  # may change

        y_true_t = Variable(one_hot(y_true.data.cpu())).cuda()
        #y_true=y_true.transpose(1, 2).transpose(2, 3).contiguous().view(-1, 2)
        y_true_t = y_true_t.transpose(1, 2).transpose(2, 3).contiguous().view(-1, 2)

        sum_r = y_true_t.sum(0)  # [1,2]

        weights = 1.0 - sum_r / sum_r.sum(0)
        weight1=torch.from_numpy(weights.data.cpu().numpy()).cuda(0)


        return F.cross_entropy(y_pred,y_true,weight1)



    def __call__(self, y_pred, y_true):

        return self.my_ce_loss(y_pred,y_true)

#=============for balanced_sigmoid_cross_entropy==============
class Balanced_CE(nn.Module):
    '''
     balanced_sigmoid_cross_entropy
     input is logits before sigmoid
    '''

    # binary cross entropy loss in 2D
    def __init__(self):
        super(Balanced_CE, self).__init__()
        self.bce_loss=nn.BCEWithLogitsLoss()
    def _get_balanced_sigmoid_cross_entropy(self, x):
        count_neg = torch.sum(1. - x)
        count_pos = torch.sum(x)
        beta = count_neg / (count_neg + count_pos)
        pos_weight = beta / (1 - beta)
        cost = torch.nn.BCEWithLogitsLoss(size_average=True, reduce=True,
                                          pos_weight=pos_weight)  # using pos_weight not weight
        return cost, 1 - beta

    def forward(self, input, target):
        loss=0
        if target.sum()>0.0:
           crition_seg,beta_seg=self._get_balanced_sigmoid_cross_entropy(target)
           #loss+=crition_seg(input,target)*beta_seg
           loss += crition_seg(input, target)
        else:
            loss+=self.bce_loss(input,target)
        return loss


class Weighted_MSE(nn.Module):
    '''
     weighted mse loss  as described in  Holistically-Nested Edge Detection
    '''
    # binary cross entropy loss in 2D
    def __init__(self):
        super(Weighted_MSE, self).__init__()
        self.MSE=nn.MSELoss()
    def forward(self,x,out_ae,out_seg):
        '''

        :param x: unl_img
        :param out_ae:
        :param out_seg:
        :return:
        '''
        n, c, h, w = x.size()
        bf_thresh=0.5
        # out_bf=out_seg.transpose(1, 2).transpose(2, 3).contiguous().view(1, -1)
        # pos_index=(out_seg>bf_thresh)# obtain true or false array
        # neg_index=(out_seg<=bf_thresh)
        pos_idx=np.zeros(shape=(n,1,h,w),dtype=np.uint8)
        neg_idx=np.zeros(shape=(n,1,h,w),dtype=np.uint8)
        pos_idx[out_seg.data.cpu().numpy()>bf_thresh]=1
        neg_idx[out_seg.data.cpu().numpy() <= bf_thresh] = 1
        pos_num=pos_idx.sum()
        neg_num=neg_idx.sum()
        pos_ratio=pos_num*1./(pos_num+neg_num)
        neg_ratio=1-pos_ratio

        pos_idx=torch.from_numpy(pos_idx).cuda(0)
        neg_idx = torch.from_numpy(neg_idx).cuda(0)

        x_pos=x.masked_select((pos_idx))
        x_neg=x.masked_select((neg_idx))

        out_ae_pos=out_ae.masked_select((pos_idx))
        out_ae_neg = out_ae.masked_select((neg_idx))

        # out_seg_pos = out_seg.masked_selected(torch.from_numpy(pos_idx)).cuda(0)
        # out_seg_neg = out_seg.masked_selected(torch.from_numpy(neg_idx)).cuda(0)

        loss=pos_ratio*self.MSE(out_ae_neg,x_neg)+neg_ratio*self.MSE(out_ae_pos,x_pos)

        return loss




class BCE2D(nn.Module):
    '''
     weighted binary entropy loss  as described in  Holistically-Nested Edge Detection
    '''
    # binary cross entropy loss in 2D
    def __init__(self):
        super(BCE2D, self).__init__()

    def forward(self,input, target):
        n, c, h, w = input.size()
        # assert(max(target) == 1)
        log_p = input.transpose(1, 2).transpose(2, 3).contiguous().view(1, -1)  # [1,1,384,209]==>[1,80256]
        target_t = target.transpose(1, 2).transpose(2, 3).contiguous().view(1, -1)
        target_trans = target_t.clone()

        pos_index = (target_t > 0)  # [1,80256]  dtype=torch.uint8 >0处为1，其他位置为0
        neg_index = (target_t == 0)  # [1,80256]
        target_trans[pos_index] = 1
        target_trans[neg_index] = 0
        pos_index = pos_index.data.cpu().numpy().astype(bool)
        neg_index = neg_index.data.cpu().numpy().astype(bool)  # 转换为bool后统计正负样本值
        weight = torch.Tensor(log_p.size()).fill_(0)  # [1,80256]
        weight = weight.numpy()
        pos_num = pos_index.sum()  # 13061
        neg_num = neg_index.sum()  # 67195
        sum_num = pos_num + neg_num
        weight[pos_index] = neg_num * 1.0 / sum_num
        weight[neg_index] = pos_num * 1.0 / sum_num
        weight = torch.from_numpy(weight)
        weight = weight.cuda()

        loss = F.binary_cross_entropy(log_p, target_t, weight, size_average=True)

        return loss
#====================================weighted bce+laplace edge loss======================
def _cross_entropy(logits,labels):
    return torch.mean((1 - labels) * logits + torch.log(1 + torch.exp(-logits)))

def _weighted_cross_entropy(logits,labels,alpha=0.5):
    count_neg = torch.sum(1. - labels)
    count_pos = torch.sum(labels)
    beta = count_neg / (count_neg + count_pos)
    pos_weight = beta / (1 - beta)
    #alpha=pos_weight

    return torch.mean((1 - alpha) * ((1 - labels) * logits + torch.log(1 + torch.exp(-logits))) + (2 * alpha - 1) * labels * torch.log(1 + torch.exp(-logits)))

class EdgeHoldLoss(nn.Module):
    def __init__(self):
        super().__init__()
        laplace = torch.FloatTensor([[-1,-1,-1,],[-1,8,-1],[-1,-1,-1]]).view([1,1,3,3])
        #filter shape in Pytorch: out_channel, in_channel, height, width
        self.laplace = nn.Parameter(data=laplace,requires_grad=False)# requires_grad=False（default=True）导致该卷积核不可训练，直接定义提取边缘特征了   含义是将一个固定不可训练的tensor转换成可以训练的类型parameter
    def torchLaplace(self,x):
        edge = F.conv2d(x,self.laplace.cuda(0),padding=1)#out = F.conv2d(x, w, b, stride=1, padding=1)
        edge = torch.abs(torch.tanh(edge))
        return edge
    def forward(self,y_pred,y_true,mode=None):
        #y_pred = nn.Sigmoid()(y_pred)
        y_true_edge = self.torchLaplace(y_true)
        y_pred_edge = self.torchLaplace(y_pred)
        edge_loss = _cross_entropy(y_pred_edge,y_true_edge)

        #seg_loss = _weighted_cross_entropy(y_pred,y_true)

        return edge_loss




#===================================bce+iou+ssim=========================================
def one_hot(label, n_classes, requires_grad=True):
    """Return One Hot Label"""
    device = label.device
    one_hot_label = torch.eye(
        n_classes, device=device, requires_grad=requires_grad)[label]
    one_hot_label = one_hot_label.transpose(1, 3).transpose(2, 3)

    return one_hot_label

class BoundaryLoss(nn.Module):
    """Boundary Loss proposed in:
    Alexey Bokhovkin et al., Boundary Loss for Remote Sensing Imagery Semantic Segmentation
    https://arxiv.org/abs/1905.07852
    """

    def __init__(self, theta0=3, theta=5):
        super().__init__()

        self.theta0 = theta0
        self.theta = theta

    def forward(self, pred, gt):
        """
        Input:
            - pred: the output from model (before softmax)
                    shape (N, C, H, W)
            - gt: ground truth map
                    shape (N, H, w)
        Return:
            - boundary loss, averaged over mini-bathc
        """

        n, c, _, _ = pred.shape

        # softmax so that predicted map can be distributed in [0, 1]
        pred = torch.softmax(pred, dim=1)#[8,1,224,224]

        # one-hot vector of ground truth
        if c==1:
            one_hot_gt =gt
        else:
            one_hot_gt = one_hot(gt, c)#[8,224,224]==>[8,1,224,224]

        # boundary map
        gt_b = F.max_pool2d(
            1 - one_hot_gt, kernel_size=self.theta0, stride=1, padding=(self.theta0 - 1) // 2)#[8,1,224,224]
        gt_b -= 1 - one_hot_gt

        pred_b = F.max_pool2d(
            1 - pred, kernel_size=self.theta0, stride=1, padding=(self.theta0 - 1) // 2)
        pred_b -= 1 - pred

        # extended boundary map
        gt_b_ext = F.max_pool2d(
            gt_b, kernel_size=self.theta, stride=1, padding=(self.theta - 1) // 2)#[8,1,224,224]

        pred_b_ext = F.max_pool2d(
            pred_b, kernel_size=self.theta, stride=1, padding=(self.theta - 1) // 2)#[8,1,224,224]

        # reshape
        gt_b = gt_b.view(n, c, -1)#[8,1,50176]
        pred_b = pred_b.view(n, c, -1)
        gt_b_ext = gt_b_ext.view(n, c, -1)
        pred_b_ext = pred_b_ext.view(n, c, -1)

        # Precision, Recall
        P = torch.sum(pred_b * gt_b_ext, dim=2) / (torch.sum(pred_b, dim=2) + 1e-7)#[8,1]
        R = torch.sum(pred_b_ext * gt_b, dim=2) / (torch.sum(gt_b, dim=2) + 1e-7)

        # Boundary F1 Score
        BF1 = 2 * P * R / (P + R + 1e-7)#[8,1]

        # summing BF1 Score for each class and average over mini-batch
        loss = torch.mean(1 - BF1)#不指定任何参数就是所有元素的算术平均值

        return loss
class bce_edge_loss(nn.Module):
    def __init__(self, batch=True,use_edge=False,use_wiou=False,use_mask=False,gamma=0):
        super(bce_edge_loss, self).__init__()
        self.batch = batch
        self.bce_loss = nn.BCELoss()
        self.use_edge=use_edge
        self.use_wiou=use_wiou
        self.weight=2.0
        self.edge_loss=EdgeHoldLoss()
        #self.edge_loss=EdgeLoss_sig()#leads to worse performance!
        self.use_mask=use_mask
        self.gamma=gamma

    def soft_dice_coeff(self, y_true, y_pred):
        smooth = 1.0  # may change
        if self.batch:
            i = torch.sum(y_true)#对二维或多维矩阵的所有元素求和
            j = self.weight*torch.sum(y_pred)
            intersection = torch.sum(y_true * y_pred)
        else:
            i = y_true.sum(1).sum(1).sum(1)#only for batch=1
            j = y_pred.sum(1).sum(1).sum(1)
            intersection = (y_true * y_pred).sum(1).sum(1).sum(1)
        score = (2. * intersection + smooth) / (i + j + smooth)
        # score = (intersection + smooth) / (i + j - intersection + smooth)#iou
        return score.mean()

    def _iou(self,pred, target, size_average=True):

        b = pred.shape[0]
        IoU = 0.0
        for i in range(0, b):
            # compute the IoU of the foreground
            Iand1 = torch.sum(target[i, :, :, :] * pred[i, :, :, :])
            Ior1 = torch.sum(target[i, :, :, :]) + torch.sum(pred[i, :, :, :]) - Iand1
            IoU1 = Iand1 / Ior1

            # IoU loss is (1-IoU1)
            IoU = IoU + (1 - IoU1)

        return IoU / b

    def weighted_iou(self,pred, target, size_average=True):
        '''
        If the number of object pixels in a batch is low,
        a misclassification of the objects by a few pixels causes a large IoU loss. Thus,
        the conventional IoU loss is multiplied by the ratio of the union area
        ref:Domain Adaptive Transfer Attack-Based Segmentation Networks for Building Extraction From Aerial Images
        :param pred:
        :param target:
        :param size_average:
        :return:
        '''
        b = pred.shape[0]
        pix_Num=pred.shape[1]*pred.shape[2]*pred.shape[3]

        IoU = 0.0
        for i in range(0, b):
            # compute the IoU of the foreground
            Iand1 = torch.sum(target[i, :, :, :] * pred[i, :, :, :])
            Ior1 = torch.sum(target[i, :, :, :]) + torch.sum(pred[i, :, :, :]) - Iand1
            #IoU1 = Iand1 / Ior1
            IoU+=(Ior1-Iand1)/pix_Num

            # IoU loss is (1-IoU1)
            #IoU = IoU + (1 - IoU1)

        return IoU / b

    def weighted_iou_1D(self,pred, target, size_average=True):
        '''
        If the number of object pixels in a batch is low,
        a misclassification of the objects by a few pixels causes a large IoU loss. Thus,
        the conventional IoU loss is multiplied by the ratio of the union area
        ref:Domain Adaptive Transfer Attack-Based Segmentation Networks for Building Extraction From Aerial Images
        :param pred:
        :param target:
        :param size_average:
        :return:
        '''
        #b = pred.shape[0]
        pix_Num=pred.shape[0]
        IoU = 0.0
        Iand1 = torch.sum(target* pred)
        Ior1 = torch.sum(target) + torch.sum(pred) - Iand1

        IoU += (Ior1 - Iand1) / pix_Num

        # for i in range(0, b):
        #     # compute the IoU of the foreground
        #     Iand1 = torch.sum(target[i, :, :, :] * pred[i, :, :, :])
        #     Ior1 = torch.sum(target[i, :, :, :]) + torch.sum(pred[i, :, :, :]) - Iand1
        #     #IoU1 = Iand1 / Ior1
        #     IoU+=(Ior1-Iand1)/pix_Num
        #
        #     # IoU loss is (1-IoU1)
        #     #IoU = IoU + (1 - IoU1)

        return IoU


    def weighted_bce_1D(self,pred, target):

        bce_loss=nn.BCELoss(reduction='none')
        loss=bce_loss(pred,target)#(target>1).sum() (target==0).sum()
        # weight=pred**self.gamma
        # loss=weight*loss
        #weight=torch.zeros_like(pred)
        # for i in range(pred.shape[0]):#two slow for computing loss using for...
        #     if target[i]==1.0:
        #         weight[i]=pred[i]**self.gamma
        #     else:
        #         weight[i]=(1-pred[i])**self.gamma
        pred0=1-pred
        target0=1-target
        weight=pred**self.gamma*target+pred0**self.gamma*target0#weight.sum()

        #weight = (pred* target + pred0* target0)** self.gamma#wrong code, note that the eq.(2) is one-hot label


        loss1 = weight * loss#loss2=(loss<0).sum()  (loss>0).sum()  (loss==0).sum()

        return loss1.mean()#loss.sum()



    def soft_dice_loss(self, y_true, y_pred):
        loss = 1 - self.soft_dice_coeff(y_true, y_pred)
        return loss




    def __call__(self, y_pred, y_true):

        if self.use_mask:
            n, c, h, w = y_pred.size()
            target_mask = (y_true >= 0) * (y_true < 200)  # ignore value=255 when calculating loss
            y_true = y_true[target_mask]
            y_pred=y_pred[target_mask]
            # y_pred = y_pred.transpose(1, 2).transpose(2, 3).contiguous()
            # y_pred = y_pred[target_mask.view(n, h, w, 1).repeat(1, 1, 1, c)].view(-1, c)
            if self.gamma>0:
                a=self.weighted_bce_1D(y_pred,y_true)
            else:
                a = self.bce_loss(y_pred, y_true)  # 0.7775
            b = self.weighted_iou_1D(y_pred, y_true)

        else:
            a = self.bce_loss(y_pred, y_true)  # 0.7775
            b = self.weighted_iou(y_pred, y_true)
            d = self.edge_loss(y_pred, y_true)  # 0.8*(a+b+c)+0.2*d



        if self.use_edge:
            return a + b + d
        elif self.use_wiou:
            return b
        return a+b

#====================weighted bce_loss====================================
class WeightedBCEWithLogitsLoss(nn.Module):

    def __init__(self, size_average=True):
        super(WeightedBCEWithLogitsLoss, self).__init__()
        self.size_average = size_average
        '''
        weighted_bce_loss(D_out, 
                                    Variable(torch.FloatTensor(D_out.data.size()).fill_(source_label)).cuda(
                                        args.gpu), weight_map, Epsilon, Lambda_local)
        '''

    def weighted(self, input, target, weight, alpha, beta):
        if not (target.size() == input.size()):
            raise ValueError("Target size ({}) must be the same as input size ({})".format(target.size(), input.size()))

        max_val = (-input).clamp(min=0)#[4,1]  # equals to F.relu
        loss = input - input * target + max_val + ((-max_val).exp() + (-input - max_val).exp()).log()#[4,1]

        if weight is not None:
            loss = alpha * loss + beta * loss * weight

        if self.size_average:
            return loss.mean()
        else:
            return loss.sum()

    def forward(self, input, target, weight, alpha, beta):
        if weight is not None:
            return self.weighted(input, target, weight, alpha, beta)
        else:
            return self.weighted(input, target, None, alpha, beta)

#===============for edge loss ref:Parsing very high resolution urban scene images by learning deep ConvNets with edge-aware loss===============

# import torch
# import torch.nn as nn
# import torch.nn.functional as F
#
# import numpy as np


class OhemCELoss(nn.Module):
    def __init__(self, thresh, n_min, ignore_lb=255, *args, **kwargs):
        super(OhemCELoss, self).__init__()
        self.thresh = thresh
        self.n_min = n_min
        self.ignore_lb = ignore_lb
        self.criteria = nn.CrossEntropyLoss(ignore_index=ignore_lb)

    def forward(self, logits, labels):
        N, C, H, W = logits.size()
        n_pixs = N * H * W
        logits = logits.permute(0, 2, 3, 1).contiguous().view(-1, C)
        labels = labels.view(-1)
        with torch.no_grad():
            scores = F.softmax(logits, dim=1)
            labels_cpu = labels
            invalid_mask = labels_cpu == self.ignore_lb
            labels_cpu[invalid_mask] = 0
            picks = scores[torch.arange(n_pixs), labels_cpu]
            picks[invalid_mask] = 1
            sorteds, _ = torch.sort(picks)
            thresh = self.thresh if sorteds[self.n_min] < self.thresh else sorteds[self.n_min]
            labels[picks > thresh] = self.ignore_lb
        ## TODO: here see if torch or numpy is faster
        labels = labels.clone()
        loss = self.criteria(logits, labels)
        return loss


class ECELoss(nn.Module):
    def __init__(self, thresh, n_min, n_classes=19, alpha=1, radius=1, beta=0.5, ignore_lb=255, mode='ohem', *args,
                 **kwargs):
        super(ECELoss, self).__init__()
        self.thresh = thresh
        self.n_min = n_min
        self.ignore_lb = ignore_lb
        self.n_classes = n_classes
        self.alpha = alpha
        self.radius = radius
        self.beta = beta

        if mode == 'ohem':
            self.criteria = OhemCELoss(thresh, n_min, ignore_lb=ignore_lb)
        elif mode == 'ce':
            self.criteria = nn.CrossEntropyLoss(ignore_index=ignore_lb)
        else:
            raise Exception('No %s loss, plase choose form ohem and ce' % mode)

        self.edge_criteria = EdgeLoss(self.n_classes, self.alpha, self.radius)

    def forward(self, logits, labels):
        if self.beta > 0:
            return self.criteria(logits, labels) + self.beta * self.edge_criteria(logits, labels)
        else:
            return self.criteria(logits, labels)


class EdgeLoss(nn.Module):
    def __init__(self, n_classes=19, radius=1, alpha=1):
        super(EdgeLoss, self).__init__()
        self.n_classes = n_classes
        self.radius = radius
        self.alpha = alpha

    def forward(self, logits, label):
        prediction = F.softmax(logits, dim=1)
        ks = 2 * self.radius
        filt1 = torch.ones(1, 1, ks, ks)
        filt1[:, :, self.radius:2 * self.radius, self.radius:2 * self.radius] = -8
        filt1.requires_grad = False
        filt1 = filt1.cuda()
        label = label.unsqueeze(1)
        lbedge = F.conv2d(label.float(), filt1, bias=None, stride=1, padding=self.radius)
        lbedge = 1 - torch.eq(lbedge, 0).float()

        filt2 = torch.ones(self.n_classes, 1, ks, ks)
        filt2[:, :, self.radius:2 * self.radius, self.radius:2 * self.radius] = -8
        filt2.requires_grad = False
        filt2 = filt2.cuda()
        prededge = F.conv2d(prediction.float(), filt2, bias=None,
                            stride=1, padding=self.radius, groups=self.n_classes)

        norm = torch.sum(torch.pow(prededge, 2), 1).unsqueeze(1)
        prededge = norm / (norm + self.alpha)

        # mask = lbedge.float()
        # num_positive = torch.sum((mask==1).float()).float()
        # num_negative = torch.sum((mask==0).float()).float()

        # mask[mask == 1] = 1.0 * num_negative / (num_positive + num_negative)
        # mask[mask == 0] = 1.5 * num_positive / (num_positive + num_negative)

        # cost = torch.nn.functional.binary_cross_entropy(
        # prededge.float(),lbedge.float(), weight=mask, reduce=False)
        # return torch.mean(cost)
        return BinaryDiceLoss()(prededge.float(), lbedge.float())

class EdgeLoss_sig(nn.Module):
    def __init__(self, n_classes=1, radius=1, alpha=1):
        super(EdgeLoss_sig, self).__init__()
        self.n_classes = n_classes
        self.radius = radius
        self.alpha = alpha

    def forward(self, prediction, label):
        #prediction = F.softmax(logits, dim=1)
        ks = 2 * self.radius
        filt1 = torch.ones(1, 1, ks, ks)
        filt1[:, :, self.radius:2 * self.radius, self.radius:2 * self.radius] = -8
        filt1.requires_grad = False
        filt1 = filt1.cuda()
        label = label
        lbedge = F.conv2d(label.float(), filt1, bias=None, stride=1, padding=self.radius)
        lbedge = 1 - torch.eq(lbedge, 0).float()

        filt2 = torch.ones(self.n_classes, 1, ks, ks)
        filt2[:, :, self.radius:2 * self.radius, self.radius:2 * self.radius] = -8
        filt2.requires_grad = False
        filt2 = filt2.cuda()
        prededge = F.conv2d(prediction.float(), filt2, bias=None,
                            stride=1, padding=self.radius, groups=self.n_classes)

        norm = torch.sum(torch.pow(prededge, 2), 1).unsqueeze(1)
        prededge = norm / (norm + self.alpha)

        # mask = lbedge.float()
        # num_positive = torch.sum((mask==1).float()).float()
        # num_negative = torch.sum((mask==0).float()).float()

        # mask[mask == 1] = 1.0 * num_negative / (num_positive + num_negative)
        # mask[mask == 0] = 1.5 * num_positive / (num_positive + num_negative)

        # cost = torch.nn.functional.binary_cross_entropy(
        # prededge.float(),lbedge.float(), weight=mask, reduce=False)
        # return torch.mean(cost)
        return BinaryDiceLoss()(prededge.float(), lbedge.float())

class BinaryDiceLoss(nn.Module):
    """Dice loss of binary class
    Args:
        smooth: A float number to smooth loss, and avoid NaN error, default: 1
        p: Denominator value: \sum{x^p} + \sum{y^p}, default: 2
        predict: A tensor of shape [N, *]
        target: A tensor of shape same with predict
        reduction: Reduction method to apply, return mean over batch if 'mean',
            return sum if 'sum', return a tensor of shape [N,] if 'none'
    Returns:
        Loss tensor according to arg reduction
    Raise:
        Exception if unexpected reduction
    """

    def __init__(self, smooth=1, p=2):
        super(BinaryDiceLoss, self).__init__()
        self.smooth = smooth
        self.p = p

    def forward(self, predict, target):
        assert predict.shape[0] == target.shape[0], "predict & target batch size don't match"
        predict = predict.contiguous().view(predict.shape[0], -1)
        target = target.contiguous().view(target.shape[0], -1)

        num = 2 * torch.sum(torch.mul(predict, target), dim=1) + self.smooth
        den = torch.sum(predict.pow(self.p) + target.pow(self.p), dim=1) + self.smooth

        loss = 1 - num / den
        return loss.sum()


if __name__ == '__main__':
    # criteria1 = OhemCELoss(thresh=0.7, n_min=16*20*20//16).cuda()
    # criteria2 = OhemCELoss(thresh=0.7, n_min=16*20*20//16).cuda()
    criteria1 = ECELoss(thresh=0.7, n_min=16 * 20 * 20 // 16).cuda()
    criteria2 = ECELoss(thresh=0.7, n_min=16 * 20 * 20 // 16).cuda()

    net1 = nn.Sequential(
        nn.Conv2d(3, 19, kernel_size=3, stride=2, padding=1),
    )
    net1.cuda()
    net1.train()
    net2 = nn.Sequential(
        nn.Conv2d(3, 19, kernel_size=3, stride=2, padding=1),
    )
    net2.cuda()
    net2.train()

    with torch.no_grad():
        inten = torch.randn(16, 3, 20, 20).cuda()
        lbs = torch.randint(0, 19, [16, 20, 20]).cuda()
        lbs[1, 10, 10] = 255

    logits1 = net1(inten)
    logits1 = F.interpolate(logits1, inten.size()[2:], mode='bilinear')
    logits2 = net2(inten)
    logits2 = F.interpolate(logits2, inten.size()[2:], mode='bilinear')

    loss1 = criteria1(logits1, lbs)
    loss2 = criteria2(logits2, lbs)
    loss = loss1 + loss2
    loss.backward()
    print('Done')

