#   Copyright (c) 2020 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import six
import abc
import numpy as np

import paddle

__all__ = ['Metric', 'Accuracy', 'Precision', 'Recall', 'Auc']


def _is_numpy_(var):
    return isinstance(var, (np.ndarray, np.generic))


@six.add_metaclass(abc.ABCMeta)
class Metric(object):
    """
    Base class for metric, encapsulates metric logic and APIs
    Usage:
        
        m = SomeMetric()
        for prediction, label in ...:
            m.update(prediction, label)
        m.accumulate()
        
    Advanced usage for :code:`compute`:

    Metric calculation can be accelerated by calculating metric states
    from model outputs and labels by build-in operators not by Python/NumPy
    in :code:`compute`, metric states will be fetched as NumPy array and
    call :code:`update` with states in NumPy format.
    Metric calculated as follows (operations in Model and Metric are
    indicated with curly brackets, while data nodes not):
                 inputs & labels              || ------------------
                       |                      ||
                    {model}                   ||
                       |                      ||
                outputs & labels              ||
                       |                      ||    tensor data
                {Metric.compute}              ||
                       |                      ||
              metric states(tensor)           ||
                       |                      ||
                {fetch as numpy}              || ------------------
                       |                      ||
              metric states(numpy)            ||    numpy data
                       |                      ||
                {Metric.update}               \/ ------------------
    Examples:
        
        For :code:`Accuracy` metric, which takes :code:`pred` and :code:`label`
        as inputs, we can calculate the correct prediction matrix between
        :code:`pred` and :code:`label` in :code:`compute`.
        For examples, prediction results contains 10 classes, while :code:`pred`
        shape is [N, 10], :code:`label` shape is [N, 1], N is mini-batch size,
        and we only need to calculate accurary of top-1 and top-5, we could
        calculate the correct prediction matrix of the top-5 scores of the
        prediction of each sample like follows, while the correct prediction
        matrix shape is [N, 5].

        .. code-block:: python
            def compute(pred, label):
                # sort prediction and slice the top-5 scores
                pred = paddle.argsort(pred, descending=True)[:, :5]
                # calculate whether the predictions are correct
                correct = pred == label
                return paddle.cast(correct, dtype='float32')

        With the :code:`compute`, we split some calculations to OPs (which
        may run on GPU devices, will be faster), and only fetch 1 tensor with
        shape as [N, 5] instead of 2 tensors with shapes as [N, 10] and [N, 1].
        :code:`update` can be define as follows:

        .. code-block:: python
            def update(self, correct):
                accs = []
                for i, k in enumerate(self.topk):
                    num_corrects = correct[:, :k].sum()
                    num_samples = len(correct)
                    accs.append(float(num_corrects) / num_samples)
                    self.total[i] += num_corrects
                    self.count[i] += num_samples
                return accs
    """

    def __init__(self):
        pass

    @abc.abstractmethod
    def reset(self):
        """
        Reset states and result
        """
        raise NotImplementedError("function 'reset' not implemented in {}.".
                                  format(self.__class__.__name__))

    @abc.abstractmethod
    def update(self, *args):
        """
        Update states for metric

        Inputs of :code:`update` is the outputs of :code:`Metric.compute`,
        if :code:`compute` is not defined, the inputs of :code:`update`
        will be flatten arguments of **output** of mode and **label** from data:
        :code:`update(output1, output2, ..., label1, label2,...)`

        see :code:`Metric.compute`
        """
        raise NotImplementedError("function 'update' not implemented in {}.".
                                  format(self.__class__.__name__))

    @abc.abstractmethod
    def accumulate(self):
        """
        Accumulates statistics, computes and returns the metric value
        """
        raise NotImplementedError(
            "function 'accumulate' not implemented in {}.".format(
                self.__class__.__name__))

    @abc.abstractmethod
    def name(self):
        """
        Returns metric name
        """
        raise NotImplementedError("function 'name' not implemented in {}.".
                                  format(self.__class__.__name__))

    def compute(self, *args):
        """
        This API is advanced usage to accelerate metric calculating, calulations
        from outputs of model to the states which should be updated by Metric can
        be defined here, where Paddle OPs is also supported. Outputs of this API
        will be the inputs of "Metric.update".

        If :code:`compute` is defined, it will be called with **outputs**
        of model and **labels** from data as arguments, all outputs and labels
        will be concatenated and flatten and each filed as a separate argument
        as follows:
        :code:`compute(output1, output2, ..., label1, label2,...)`

        If :code:`compute` is not defined, default behaviour is to pass
        input to output, so output format will be:
        :code:`return output1, output2, ..., label1, label2,...`

        see :code:`Metric.update`
        """
        return args


class Accuracy(Metric):
    """
    Encapsulates accuracy metric logic.

    Args:
        topk (int|tuple(int)): Number of top elements to look at
            for computing accuracy. Default is (1,).
        name (str, optional): String name of the metric instance. Default
            is `acc`.

    Example by standalone:
        
        .. code-block:: python

        import numpy as np
        import paddle

        paddle.disable_static()
        x = paddle.to_tensor(np.array([
            [0.1, 0.2, 0.3, 0.4],
            [0.1, 0.4, 0.3, 0.2],
            [0.1, 0.2, 0.4, 0.3],
            [0.1, 0.2, 0.3, 0.4]]))
        y = paddle.to_tensor(np.array([[0], [1], [2], [3]]))

        m = paddle.metric.Accuracy()
        correct = m.compute(x, y)
        m.update(correct)
        res = m.accumulate()
        print(res) # 0.75


    Example with Model API:
        
        .. code-block:: python

        import paddle
        import paddle.incubate.hapi as hapi

        paddle.disable_static()
        train_dataset = hapi.datasets.MNIST(mode='train')

        model = hapi.Model(hapi.vision.LeNet(classifier_activation=None))
        optim = paddle.optimizer.Adam(
            learning_rate=0.001, parameters=model.parameters())
        model.prepare(
            optim,
            loss=paddle.nn.CrossEntropyLoss(),
            metrics=paddle.metric.Accuracy())

        model.fit(train_dataset, batch_size=64)

    """

    def __init__(self, topk=(1, ), name=None, *args, **kwargs):
        super(Accuracy, self).__init__(*args, **kwargs)
        self.topk = topk
        self.maxk = max(topk)
        self._init_name(name)
        self.reset()

    def compute(self, pred, label, *args):
        """
        Compute the top-k (maxinum value in `topk`) indices.

        Args:
            pred (Tensor): The predicted value is a Tensor wit type
                float32 or float64.
            label (Tensor): The ground truth value is a 2D Tensor, its
                shape is [batch_size, 1] and type is int64.

        Return:
            Tensor: Correct mask, a tensor with shape [batch_size, topk].
        """
        pred = paddle.argsort(pred, descending=True)[:, :self.maxk]
        correct = pred == label
        return paddle.cast(correct, dtype='float32')

    def update(self, correct, *args):
        """
        Update the metrics states (correct count and total count), in order to
        calculate cumulative accuracy of all instances. This function also
        returns the accuracy of current step.
        
        Args:
            correct: Correct mask, a tensor with shape [batch_size, topk].

        Return:
            Tensor: the accuracy of current step.
        """
        if isinstance(correct, paddle.Tensor):
            correct = correct.numpy()
        accs = []
        for i, k in enumerate(self.topk):
            num_corrects = correct[:, :k].sum()
            num_samples = len(correct)
            accs.append(float(num_corrects) / num_samples)
            self.total[i] += num_corrects
            self.count[i] += num_samples
        accs = accs[0] if len(self.topk) == 1 else accs
        return accs

    def reset(self):
        """
        Resets all of the metric state.
        """
        self.total = [0.] * len(self.topk)
        self.count = [0] * len(self.topk)

    def accumulate(self):
        """
        Computes and returns the accumulated metric.
        """
        res = []
        for t, c in zip(self.total, self.count):
            r = float(t) / c if c > 0 else 0.
            res.append(r)
        res = res[0] if len(self.topk) == 1 else res
        return res

    def _init_name(self, name):
        name = name or 'acc'
        if self.maxk != 1:
            self._name = ['{}_top{}'.format(name, k) for k in self.topk]
        else:
            self._name = [name]

    def name(self):
        """
        Return name of metric instance.
        """
        return self._name


class Precision(Metric):
    """
    Precision (also called positive predictive value) is the fraction of
    relevant instances among the retrieved instances. Refer to
    https://en.wikipedia.org/wiki/Evaluation_of_binary_classifiers

    Noted that this class manages the precision score only for binary
    classification task.

    Args:
        name (str, optional): String name of the metric instance.
            Default is `precision`.

    Example by standalone:
        
        .. code-block:: python

        import numpy as np
        import paddle

        x = np.array([0.1, 0.5, 0.6, 0.7])
        y = np.array([0, 1, 1, 1])

        m = paddle.metric.Precision()
        m.update(x, y)
        res = m.accumulate()
        print(res) # 1.0


    Example with Model API:
        
        .. code-block:: python

        import numpy as np
        
        import paddle
        import paddle.nn as nn
        import paddle.incubate.hapi as hapi
        
        class Data(paddle.io.Dataset):
            def __init__(self):
                super(Data, self).__init__()
                self.n = 1024
                self.x = np.random.randn(self.n, 10).astype('float32')
                self.y = np.random.randint(2, size=(self.n, 1)).astype('float32')
        
            def __getitem__(self, idx):
                return self.x[idx], self.y[idx]
        
            def __len__(self):
                return self.n
  
        paddle.disable_static()
        model = hapi.Model(nn.Sequential(
            nn.Linear(10, 1),
            nn.Sigmoid()
        ))
        optim = paddle.optimizer.Adam(
            learning_rate=0.001, parameters=model.parameters())
        model.prepare(
            optim,
            loss=nn.BCELoss(),
            metrics=paddle.metric.Precision())
        
        data = Data()
        model.fit(data, batch_size=16)
    """

    def __init__(self, name='precision', *args, **kwargs):
        super(Precision, self).__init__(*args, **kwargs)
        self.tp = 0  # true positive
        self.fp = 0  # false positive
        self._name = name

    def update(self, preds, labels):
        """
        Update the states based on the current mini-batch prediction results.

        Args:
            preds (numpy.ndarray): The prediction result, usually the output
                of two-class sigmoid function. It should be a vector (column
                vector or row vector) with data type: 'float64' or 'float32'.
            labels (numpy.ndarray): The ground truth (labels),
                the shape should keep the same as preds.
                The data type is 'int32' or 'int64'.
        """
        if isinstance(preds, paddle.Tensor):
            preds = preds.numpy()
        elif not _is_numpy_(preds):
            raise ValueError("The 'preds' must be a numpy ndarray or Tensor.")

        if isinstance(labels, paddle.Tensor):
            labels = labels.numpy()
        elif not _is_numpy_(labels):
            raise ValueError("The 'labels' must be a numpy ndarray or Tensor.")

        sample_num = labels.shape[0]
        preds = np.floor(preds + 0.5).astype("int32")

        for i in range(sample_num):
            pred = preds[i]
            label = labels[i]
            if pred == 1:
                if pred == label:
                    self.tp += 1
                else:
                    self.fp += 1

    def reset(self):
        """
        Resets all of the metric state.
        """
        self.tp = 0
        self.fp = 0

    def accumulate(self):
        """
        Calculate the final precision.

        Returns:
            A scaler float: results of the calculated precision.
        """
        ap = self.tp + self.fp
        return float(self.tp) / ap if ap != 0 else .0

    def name(self):
        """
        Returns metric name
        """
        return self._name


class Recall(Metric):
    """
    Recall (also known as sensitivity) is the fraction of
    relevant instances that have been retrieved over the
    total amount of relevant instances

    Refer to:
    https://en.wikipedia.org/wiki/Precision_and_recall

    Noted that this class manages the recall score only for
    binary classification task.

    Args:
        name (str, optional): String name of the metric instance.
            Default is `recall`.

    Example by standalone:
        
        .. code-block:: python

        import numpy as np
        import paddle

        x = np.array([0.1, 0.5, 0.6, 0.7])
        y = np.array([1, 0, 1, 1])

        m = paddle.metric.Recall()
        m.update(x, y)
        res = m.accumulate()
        print(res) # 2.0 / 3.0


    Example with Model API:
        
        .. code-block:: python

        import numpy as np
        
        import paddle
        import paddle.nn as nn
        import paddle.incubate.hapi as hapi
        
        class Data(paddle.io.Dataset):
            def __init__(self):
                super(Data, self).__init__()
                self.n = 1024
                self.x = np.random.randn(self.n, 10).astype('float32')
                self.y = np.random.randint(2, size=(self.n, 1)).astype('float32')
        
            def __getitem__(self, idx):
                return self.x[idx], self.y[idx]
        
            def __len__(self):
                return self.n
        
        paddle.disable_static()
        model = hapi.Model(nn.Sequential(
            nn.Linear(10, 1),
            nn.Sigmoid()
        ))
        optim = paddle.optimizer.Adam(
            learning_rate=0.001, parameters=model.parameters())
        model.prepare(
            optim,
            loss=nn.BCELoss(),
            metrics=[paddle.metric.Precision(), paddle.metric.Recall()])
        
        data = Data()
        model.fit(data, batch_size=16)
    """

    def __init__(self, name='recall', *args, **kwargs):
        super(Recall, self).__init__(*args, **kwargs)
        self.tp = 0  # true positive
        self.fn = 0  # false negative
        self._name = name

    def update(self, preds, labels):
        """
        Update the states based on the current mini-batch prediction results.

        Args:
            preds(numpy.array): prediction results of current mini-batch,
                the output of two-class sigmoid function.
                Shape: [batch_size, 1]. Dtype: 'float64' or 'float32'.
            labels(numpy.array): ground truth (labels) of current mini-batch,
                the shape should keep the same as preds.
                Shape: [batch_size, 1], Dtype: 'int32' or 'int64'.
        """
        if isinstance(preds, paddle.Tensor):
            preds = preds.numpy()
        elif not _is_numpy_(preds):
            raise ValueError("The 'preds' must be a numpy ndarray or Tensor.")

        if isinstance(labels, paddle.Tensor):
            labels = labels.numpy()
        elif not _is_numpy_(labels):
            raise ValueError("The 'labels' must be a numpy ndarray or Tensor.")

        sample_num = labels.shape[0]
        preds = np.rint(preds).astype("int32")

        for i in range(sample_num):
            pred = preds[i]
            label = labels[i]
            if label == 1:
                if pred == label:
                    self.tp += 1
                else:
                    self.fn += 1

    def accumulate(self):
        """
        Calculate the final recall.

        Returns:
            A scaler float: results of the calculated Recall.
        """
        recall = self.tp + self.fn
        return float(self.tp) / recall if recall != 0 else .0

    def reset(self):
        """
        Resets all of the metric state.
        """
        self.tp = 0
        self.fn = 0

    def name(self):
        """
        Returns metric name
        """
        return self._name


class Auc(Metric):
    """
    The auc metric is for binary classification.
    Refer to https://en.wikipedia.org/wiki/Receiver_operating_characteristic#Area_under_the_curve.
    Please notice that the auc metric is implemented with python, which may be a little bit slow.

    The `auc` function creates four local variables, `true_positives`,
    `true_negatives`, `false_positives` and `false_negatives` that are used to
    compute the AUC. To discretize the AUC curve, a linearly spaced set of
    thresholds is used to compute pairs of recall and precision values. The area
    under the ROC-curve is therefore computed using the height of the recall
    values by the false positive rate, while the area under the PR-curve is the
    computed using the height of the precision values by the recall.

    Args:
        curve (str): Specifies the mode of the curve to be computed,
            'ROC' or 'PR' for the Precision-Recall-curve. Default is 'ROC'.
        num_thresholds (int): The number of thresholds to use when
            discretizing the roc curve. Default is 4095.
            'ROC' or 'PR' for the Precision-Recall-curve. Default is 'ROC'.
        name (str, optional): String name of the metric instance. Default
            is `auc`.

    "NOTE: only implement the ROC curve type via Python now."

    Example by standalone:
        .. code-block:: python

        import numpy as np
        import paddle

        m = paddle.metric.Auc()
        
        n = 8
        class0_preds = np.random.random(size = (n, 1))
        class1_preds = 1 - class0_preds
        
        preds = np.concatenate((class0_preds, class1_preds), axis=1)
        labels = np.random.randint(2, size = (n, 1))
        
        m.update(preds=preds, labels=labels)
        res = m.accumulate()


    Example with Model API:
        
        .. code-block:: python

        import numpy as np
        import paddle
        import paddle.nn as nn
        import paddle.incubate.hapi as hapi
        
        class Data(paddle.io.Dataset):
            def __init__(self):
                super(Data, self).__init__()
                self.n = 1024
                self.x = np.random.randn(self.n, 10).astype('float32')
                self.y = np.random.randint(2, size=(self.n, 1)).astype('int64')
        
            def __getitem__(self, idx):
                return self.x[idx], self.y[idx]
        
            def __len__(self):
                return self.n
        
        paddle.disable_static()
        model = hapi.Model(nn.Sequential(
            nn.Linear(10, 2, act='softmax'),
        ))
        optim = paddle.optimizer.Adam(
            learning_rate=0.001, parameters=model.parameters())
        
        def loss(x, y):
            return nn.functional.nll_loss(paddle.log(x), y)
        
        model.prepare(
            optim,
            loss=loss,
            metrics=paddle.metric.Auc())
        data = Data()
        model.fit(data, batch_size=16)
    """

    def __init__(self,
                 curve='ROC',
                 num_thresholds=4095,
                 name='auc',
                 *args,
                 **kwargs):
        super(Auc, self).__init__(*args, **kwargs)
        self._curve = curve
        self._num_thresholds = num_thresholds

        _num_pred_buckets = num_thresholds + 1
        self._stat_pos = np.zeros(_num_pred_buckets)
        self._stat_neg = np.zeros(_num_pred_buckets)
        self._name = name

    def update(self, preds, labels):
        """
        Update the auc curve with the given predictions and labels.

        Args:
            preds (numpy.array): An numpy array in the shape of
                (batch_size, 2), preds[i][j] denotes the probability of
                classifying the instance i into the class j.
            labels (numpy.array): an numpy array in the shape of
                (batch_size, 1), labels[i] is either o or 1,
                representing the label of the instance i.
        """
        if isinstance(labels, paddle.Tensor):
            labels = labels.numpy()
        elif not _is_numpy_(labels):
            raise ValueError("The 'labels' must be a numpy ndarray or Tensor.")

        if isinstance(preds, paddle.Tensor):
            preds = preds.numpy()
        elif not _is_numpy_(preds):
            raise ValueError("The 'preds' must be a numpy ndarray or Tensor.")

        for i, lbl in enumerate(labels):
            value = preds[i, 1]
            bin_idx = int(value * self._num_thresholds)
            assert bin_idx <= self._num_thresholds
            if lbl:
                self._stat_pos[bin_idx] += 1.0
            else:
                self._stat_neg[bin_idx] += 1.0

    @staticmethod
    def trapezoid_area(x1, x2, y1, y2):
        return abs(x1 - x2) * (y1 + y2) / 2.0

    def accumulate(self):
        """
        Return the area (a float score) under auc curve

        Return:
            float: the area under auc curve
        """
        tot_pos = 0.0
        tot_neg = 0.0
        auc = 0.0

        idx = self._num_thresholds
        while idx >= 0:
            tot_pos_prev = tot_pos
            tot_neg_prev = tot_neg
            tot_pos += self._stat_pos[idx]
            tot_neg += self._stat_neg[idx]
            auc += self.trapezoid_area(tot_neg, tot_neg_prev, tot_pos,
                                       tot_pos_prev)
            idx -= 1

        return auc / tot_pos / tot_neg if tot_pos > 0.0 and tot_neg > 0.0 else 0.0

    def reset(self):
        """
        Reset states and result
        """
        _num_pred_buckets = self._num_thresholds + 1
        self._stat_pos = np.zeros(_num_pred_buckets)
        self._stat_neg = np.zeros(_num_pred_buckets)

    def name(self):
        """
        Returns metric name
        """
        return self._name
