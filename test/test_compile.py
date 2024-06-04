# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
import argparse
from typing import Any

import pytest

import torch

from tensordict import assert_close, tensorclass, TensorDict, TensorDictParams
from tensordict.nn import TensorDictModule as Mod, TensorDictSequential as Seq


class TestTD:
    def test_tensor_output(self):
        def add_one(td):
            return td["a", "b"] + 1

        add_one_c = torch.compile(add_one, fullgraph=True)
        data = TensorDict({"a": {"b": 0}})
        assert add_one(data) == 1
        assert add_one_c(data) == 1
        assert add_one_c(data + 1) == 2

    def test_td_output(self):
        def add_one(td):
            td["a", "c"] = td["a", "b"] + 1
            return td

        add_one_c = torch.compile(add_one, fullgraph=True)
        data = TensorDict({"a": {"b": 0}})
        assert add_one(data.clone())["a", "c"] == 1
        assert add_one_c(data.clone())["a", "c"] == 1
        assert add_one_c(data) is data

    @pytest.mark.parametrize("index_type", ["slice", "tensor", "int"])
    def test_td_index(self, index_type):
        if index_type == "slice":

            def add_one(td):
                return td[:2] + 1

        elif index_type == "tensor":

            def add_one(td):
                return td[torch.tensor([0, 1])] + 1

        elif index_type == "int":

            def add_one(td):
                return td[0] + 1

        add_one_c = torch.compile(add_one, fullgraph=True)
        data = TensorDict({"a": {"b": torch.arange(3)}}, [3])
        if index_type == "int":
            assert (add_one(data)["a", "b"] == 1).all()
            assert (add_one_c(data)["a", "b"] == 1).all()
            assert add_one_c(data).shape == torch.Size([])
        else:
            assert (add_one(data)["a", "b"] == torch.arange(1, 3)).all()
            assert (add_one_c(data)["a", "b"] == torch.arange(1, 3)).all()
            assert add_one_c(data).shape == torch.Size([2])

    def test_stack(self):
        def stack_tds(td0, td1):
            return TensorDict.stack([td0, td1])
            # return torch.stack([td0, td1])

        stack_tds_c = torch.compile(stack_tds, fullgraph=True)
        data0 = TensorDict({"a": {"b": torch.arange(3)}}, [3])
        data1 = TensorDict({"a": {"b": torch.arange(3)}}, [3])
        assert (stack_tds(data0, data1) == stack_tds_c(data0, data1)).all()

    def test_cat(self):
        def cat_tds(td0, td1):
            return TensorDict.cat([td0, td1])

        cat_tds_c = torch.compile(cat_tds, fullgraph=True)
        data0 = TensorDict({"a": {"b": torch.arange(3)}}, [3])
        data1 = TensorDict({"a": {"b": torch.arange(3)}}, [3])
        assert (cat_tds(data0, data1) == cat_tds_c(data0, data1)).all()

    def test_reshape(self):
        def reshape(td):
            return td.reshape(2, 2)

        reshape_c = torch.compile(reshape, fullgraph=True)
        data = TensorDict({"a": {"b": torch.arange(4)}}, [4])
        assert (reshape(data) == reshape_c(data)).all()

    def test_unbind(self):
        def unbind(td):
            return td.unbind(0)

        unbind_c = torch.compile(unbind, fullgraph=True)
        data = TensorDict({"a": {"b": torch.arange(4)}}, [4])
        assert (unbind(data)[-1] == unbind_c(data)[-1]).all()

    def test_items(self):
        def items(td):
            keys, vals = zip(*td.items(True, True))
            return keys, vals

        items_c = torch.compile(items, fullgraph=True)
        data = TensorDict({"a": {"b": torch.arange(4)}}, [4])
        keys, vals = items(data)
        keys_c, vals_c = items_c(data)

        def assert_eq(x, y):
            assert (x == y).all()

        assert keys == keys_c
        torch.utils._pytree.tree_map(assert_eq, vals, vals_c)

    @pytest.mark.parametrize("recurse", [True, False])
    def test_clone(self, recurse):
        def clone(td: TensorDict):
            return td.clone(recurse=recurse)

        clone_c = torch.compile(clone, fullgraph=True)
        data = TensorDict({"a": {"b": 0, "c": 1}})
        assert_close(clone_c(data), clone(data))
        assert clone_c(data) is not data
        if recurse:
            assert clone_c(data)["a", "b"] is not data["a", "b"]
        else:
            assert clone_c(data)["a", "b"] is data["a", "b"]


@tensorclass
class MyClass:
    a: "MyClass"
    b: Any = None
    c: Any = None


class TestTC:
    def test_tc_tensor_output(self):
        def add_one(td):
            return td.a.b + 1

        add_one_c = torch.compile(add_one, fullgraph=True)
        data = MyClass(MyClass(a=None, b=torch.zeros(())))
        assert add_one(data) == 1
        assert add_one_c(data) == 1
        assert add_one_c(data + 1) == 2

    def test_tc_items(self):
        def items(td):
            keys, vals = zip(*td.items(True, True))
            return keys, vals

        items_c = torch.compile(items, fullgraph=True)
        data = MyClass(MyClass(a=None, b=torch.zeros(())))
        keys, vals = items(data)
        keys_c, vals_c = items_c(data)

        def assert_eq(x, y):
            assert (x == y).all()

        assert keys == keys_c
        torch.utils._pytree.tree_map(assert_eq, vals, vals_c)

    def test_tc_output(self):
        def add_one(td):
            td.a.c = td.a.b + 1
            return td

        add_one_c = torch.compile(add_one, fullgraph=True)
        data = MyClass(a=MyClass(a=None, b=torch.zeros(())))
        assert add_one(data.clone()).a.c == 1
        assert add_one_c(data.clone()).a.c == 1
        assert add_one_c(data) is data

    def test_tc_arithmetic(self):
        def add_one(td):
            return td + 1

        data = MyClass(a=MyClass(a=None, b=torch.zeros(())))

        eager = add_one(data.clone())

        add_one_c = torch.compile(add_one, fullgraph=True)
        compiled = add_one_c(data.clone())

        assert isinstance(eager.a, MyClass)
        assert eager.a.b == 1

        assert isinstance(compiled.a, MyClass)
        # TODO: breaks because a is not cast to a MyClass but is a dict
        assert compiled.a.b == 1
        assert add_one_c(data) is not data

    def test_tc_arithmetic_other_tc(self):
        def add_self(td):
            return td + td

        data = MyClass(a=MyClass(a=None, b=torch.ones(())))

        eager = add_self(data.clone())

        add_self_c = torch.compile(add_self, fullgraph=True)
        compiled = add_self_c(data.clone())

        assert isinstance(eager.a, MyClass)
        assert eager.a.b == 2

        assert isinstance(compiled.a, MyClass)
        # TODO: breaks because a is not cast to a MyClass but is a dict
        assert compiled.a.b == 2
        assert add_self_c(data) is not data

    @pytest.mark.parametrize("index_type", ["slice", "tensor", "int"])
    def test_tc_index(self, index_type):
        if index_type == "slice":

            def index(td):
                return td[:2]

        elif index_type == "tensor":

            def index(td):
                return td[torch.tensor([0, 1])]

        elif index_type == "int":

            def index(td):
                return td[0]

        index_c = torch.compile(index, fullgraph=True)
        data = MyClass(
            a=MyClass(a=None, b=torch.arange(3), batch_size=[3]), batch_size=[3]
        )

        indexed_data_eager = index(data)
        indexed_data_compile = index_c(data)
        if index_type == "int":
            assert (indexed_data_eager.a.b == 0).all()
            assert (indexed_data_compile.a.b == 0).all()

            assert isinstance(indexed_data_eager, MyClass)
            assert isinstance(indexed_data_compile, MyClass)

            assert isinstance(indexed_data_eager.a, MyClass)
            assert isinstance(indexed_data_compile.a, MyClass)

            assert indexed_data_eager.shape == torch.Size([])
            assert indexed_data_compile.shape == torch.Size([])

        else:
            assert (indexed_data_eager.a.b == torch.arange(0, 2)).all()
            assert (indexed_data_compile.a.b == torch.arange(0, 2)).all()
            assert isinstance(indexed_data_eager, MyClass)
            assert isinstance(indexed_data_compile, MyClass)
            assert isinstance(indexed_data_eager.a, MyClass)
            assert isinstance(indexed_data_compile.a, MyClass)
            assert indexed_data_eager.shape == torch.Size([2])
            assert indexed_data_compile.shape == torch.Size([2])

    def test_tc_stack(self):
        def stack_tds(td0, td1):
            return TensorDict.stack([td0, td1])
            # return torch.stack([td0, td1])

        data0 = MyClass(
            a=MyClass(a=None, b=torch.arange(3), batch_size=[3]), batch_size=[3]
        )
        data1 = MyClass(
            a=MyClass(a=None, b=torch.arange(3, 6), batch_size=[3]), batch_size=[3]
        )
        stack_eager = stack_tds(data0, data1)

        stack_tds_c = torch.compile(stack_tds, fullgraph=True)
        stack_compile = stack_tds_c(data0, data1)

        assert (stack_eager == stack_compile).all()

    def test_tc_cat(self):
        def cat_tds(td0, td1):
            return TensorDict.cat([td0, td1])

        cat_tds_c = torch.compile(cat_tds, fullgraph=True)
        data0 = MyClass(
            a=MyClass(a=None, b=torch.arange(3), batch_size=[3]), batch_size=[3]
        )
        data1 = MyClass(
            a=MyClass(a=None, b=torch.arange(3, 6), batch_size=[3]), batch_size=[3]
        )
        assert (cat_tds(data0, data1) == cat_tds_c(data0, data1)).all()

    def test_tc_reshape(self):
        def reshape(td):
            return td.reshape(2, 2)

        reshape_c = torch.compile(reshape, fullgraph=True)
        data = MyClass(
            a=MyClass(a=None, b=torch.arange(4), batch_size=[4]), batch_size=[4]
        )
        assert (reshape(data) == reshape_c(data)).all()

    def test_tc_unbind(self):
        def unbind(td):
            return td.unbind(0)

        unbind_c = torch.compile(unbind, fullgraph=True)
        data = MyClass(
            a=MyClass(a=None, b=torch.arange(4), batch_size=[4]), batch_size=[4]
        )
        assert (unbind(data)[-1] == unbind_c(data)[-1]).all()

    @pytest.mark.parametrize("recurse", [True, False])
    def test_tc_clone(self, recurse):
        def clone(td: TensorDict):
            return td.clone(recurse=recurse)

        clone_c = torch.compile(clone, fullgraph=True)
        data = MyClass(
            a=MyClass(a=None, b=torch.arange(4), batch_size=[4]), batch_size=[4]
        )
        assert_close(clone_c(data), clone(data))
        assert clone_c(data) is not data
        if recurse:
            assert clone_c(data).a.b is not data.a.b
        else:
            assert clone_c(data).a.b is data.a.b


class TestNN:
    def test_func(self):
        td = TensorDict({"a": 0})
        module = Mod(
            lambda x: x + 1, in_keys=[(((("a",),),),)], out_keys=[(((("a",),),),)]
        )
        module_compile = torch.compile(module, fullgraph=True)

        assert_close(module(td), module_compile(td))

    def test_linear(self):
        net = torch.nn.Linear(4, 5)
        module = Mod(net, in_keys=[(((("a",),),),)], out_keys=[("c", "d")])
        module_compile = torch.compile(module, fullgraph=True)
        td = TensorDict({"a": torch.randn(32, 4)}, [32])
        assert_close(module(td), module_compile(td))

    def test_seq(self):
        net0 = torch.nn.Linear(4, 5)
        module0 = Mod(net0, in_keys=["a"], out_keys=["hidden"])
        net1 = torch.nn.Linear(5, 6)
        module1 = Mod(net1, in_keys=["hidden"], out_keys=[("c", "d")])
        module = Seq(module0, module1)
        module_compile = torch.compile(module, fullgraph=True)
        td = TensorDict({"a": torch.randn(32, 4)}, [32])
        assert_close(module(td), module_compile(td))

        assert module_compile(td) is td

    def test_seq_lmbda(self):
        net0 = torch.nn.Linear(4, 5)
        module0 = Mod(net0, in_keys=["a"], out_keys=["hidden"])
        net1 = torch.nn.Linear(5, 6)
        module1 = Mod(net1, in_keys=["hidden"], out_keys=[("c", "d")])

        def remove_hidden(td):
            del td["hidden"]
            return td

        module = Seq(lambda td: td.copy(), module0, module1, remove_hidden)
        module_compile = torch.compile(module, fullgraph=True)
        td = TensorDict({"a": torch.randn(32, 4)}, [32])
        assert_close(module(td), module_compile(td))
        assert module_compile(td) is not td


class TestFunc:
    @pytest.mark.parametrize("modif_param", [False, True])
    def test_func(self, modif_param):
        class MessUpParams(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.param = torch.nn.Parameter(torch.zeros(()))

            def forward(self, x):
                self.param.data.add_(1)
                return x

        module = torch.nn.Sequential(
            torch.nn.Linear(3, 4),
            torch.nn.ReLU(),
            torch.nn.Linear(4, 5),
        )
        if modif_param:
            module.append(MessUpParams())

        td = TensorDict.from_module(module)
        td_zero = TensorDictParams(td.data.clone())
        td_zero.zero_()

        def call(x, td):
            # TOFIX: `with` needs registering
            # with td.to_module(module):
            #     return module(x)

            params = td.to_module(module, return_swap=True)
            result = module(x)
            params.to_module(module, return_swap=True, swap_dest=td)
            return result

        call_compile = torch.compile(call, fullgraph=True)  # , backend="eager")
        x = torch.randn(2, 3)
        assert (call(x, td_zero) == 0).all()
        assert (call(x, td_zero) == 0).all()
        if modif_param:
            assert td_zero["3", "param"] == 2
        else:
            assert (td_zero == 0).all()
        # torch.testing.assert_close(call_compile(x, td_zero), module(x))
        assert (call_compile(x, td_zero) == 0).all()
        assert (call_compile(x, td_zero) == 0).all()
        if modif_param:
            assert td_zero["3", "param"] == 4
        else:
            assert (td_zero == 0).all()


if __name__ == "__main__":
    args, unknown = argparse.ArgumentParser().parse_known_args()
    pytest.main([__file__, "--capture", "no", "--exitfirst"] + unknown)