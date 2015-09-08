# -*- coding: utf-8 -*-

from __future__ import division, print_function

__all__ = ["ModelingMixin", "supports_modeling_protocol",
           "check_gradient"]

import fnmatch
import numpy as np
from collections import OrderedDict

from .compat import iteritems, izip, xrange

_EPS = 1.254e-5


class ModelingMixin(object):

    _parameters = OrderedDict()
    _frozen = dict()

    def __init__(self, **kwargs):
        self._parameters = OrderedDict(sorted(iteritems(kwargs)))
        self._frozen = dict((k, False) for k in self._parameters)

    def __getitem__(self, k):
        if "*" in k or "?" in k:
            return self.get_parameter(k)

        try:
            i = int(k)
        except ValueError:
            return self._parameters[k]
        return self._parameters.values()[i]

    def __setitem__(self, k, v):
        if "*" in k or "?" in k:
            self.set_parameter(k, v)
            return

        try:
            i = int(k)
        except ValueError:
            pass
        else:
            k = self._parameters.keys()[i]

        if k in self._parameters:
            self._parameters[k] = v
        else:
            self._parameters[k] = v
            self._frozen[k] = False

    def __getattr__(self, k):
        try:
            return self._parameters[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        if k in self._parameters:
            self._parameters[k] = v
        else:
            super(ModelingMixin, self).__setattr__(k, v)

    def __len__(self):
        return len(self._frozen) - sum(self._frozen.values())

    def get_parameter_names(self, full=False):
        if full:
            return list(self._parameters.keys())
        return [k for k in self._parameters if not self._frozen[k]]

    def get_bounds(self):
        return [(None, None) for _ in xrange(len(self))]

    def get_vector(self):
        return np.array([v for k, v in iteritems(self._parameters)
                         if not self._frozen[k]], dtype=np.float64)

    def check_vector(self, vector):
        for i, (a, b) in enumerate(self.get_bounds()):
            v = vector[i]
            if (a is not None and v < a) or (b is not None and b < v):
                return False
        return True

    def set_vector(self, vector):
        for k, v in izip(self.get_parameter_names(), vector):
            self[k] = v

    def get_value(self, *args, **kwargs):
        raise NotImplementedError("'get_value' must be implemented by "
                                  "subclasses")

    def get_gradient(self, *args, **kwargs):
        vector = self.get_vector()
        value0 = self.get_value(*args, **kwargs)
        grad = np.empty([len(vector)] + list(value0.shape), dtype=np.float64)
        for i, v in enumerate(vector):
            vector[i] = v + _EPS
            self.set_vector(vector)
            value = self.get_value(*args, **kwargs)
            vector[i] = v
            self.set_vector(vector)
            grad[i] = (value - value0) / _EPS
        return grad

    def freeze_parameter(self, parameter_name):
        any_ = False
        for k in self._frozen.keys():
            if not fnmatch.fnmatch(k, parameter_name):
                continue
            any_ = True
            self._frozen[k] = True
        if not any_:
            raise ValueError("unknown parameter '{0}'".format(parameter_name))

    def thaw_parameter(self, parameter_name):
        any_ = False
        for k in self._frozen.keys():
            if not fnmatch.fnmatch(k, parameter_name):
                continue
            any_ = True
            self._frozen[k] = False
        if not any_:
            raise ValueError("unknown parameter '{0}'".format(parameter_name))

    def get_parameter(self, parameter_name):
        params = []
        for k, v in iteritems(self._parameters):
            if not fnmatch.fnmatch(k, parameter_name):
                continue
            params.append(v)
        if len(params) == 0:
            raise ValueError("unknown parameter '{0}'".format(parameter_name))
        if len(params) == 1:
            return params[0]
        return np.array(params)

    def set_parameter(self, parameter_name, value):
        i = 0
        for k in self._parameters.keys():
            if not fnmatch.fnmatch(k, parameter_name):
                continue
            try:
                self._parameters[k] = float(value)
            except TypeError:
                self._parameters[k] = value[i]
            i += 1
        if i == 0:
            raise ValueError("unknown parameter '{0}'".format(parameter_name))

    @staticmethod
    def parameter_sort(f):
        def func(self, *args, **kwargs):
            values = f(self, *args, **kwargs)
            ret = [values[k] for k in self.get_parameter_names()]
            # Horrible hack to only return numpy array if that's what was
            # given by the wrapped function.
            if len(ret) and type(ret[0]).__module__ == np.__name__:
                return np.vstack(ret)
            return ret
        return func


def supports_modeling_protocol(obj):
    # The modeling protocol requires the object to have a length.
    try:
        len(obj)
    except TypeError:
        return False

    # Check that all of the methods are implemented.
    methods = [
        "get_value",
        "get_gradient",
        "get_parameter_names",
        "get_vector",
        "check_vector",
        "set_vector",
        "freeze_parameter",
        "thaw_parameter",
        "get_parameter",
        "set_parameter",
        "get_bounds",
    ]
    for method in methods:
        if not callable(getattr(obj, method, None)):
            return False
    return True


def check_gradient(obj, *args, **kwargs):
    eps = kwargs.pop("eps", 1.23e-5)

    grad0 = obj.get_gradient(*args, **kwargs)
    vector = obj.get_vector()
    for i, v in enumerate(vector):
        # Compute the centered finite difference approximation to the gradient.
        vector[i] = v + eps
        obj.set_vector(vector)
        p = obj.get_value(*args, **kwargs)

        vector[i] = v - eps
        obj.set_vector(vector)
        m = obj.get_value(*args, **kwargs)

        vector[i] = v
        obj.set_vector(vector)

        grad = 0.5 * (p - m) / eps
        assert np.allclose(grad0[i], grad), \
            "grad computation failed for '{0}' ({1})" \
            .format(obj.get_parameter_names()[i], i)
