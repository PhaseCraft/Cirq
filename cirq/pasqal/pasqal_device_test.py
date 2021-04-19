# Copyright 2020 The Cirq Developers
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import pytest
import sympy
import numpy as np

import cirq

from cirq.pasqal import PasqalDevice, PasqalVirtualDevice
from cirq.pasqal import TwoDQubit, ThreeDQubit


def generic_device(num_qubits) -> PasqalDevice:
    return PasqalDevice(qubits=cirq.NamedQubit.range(num_qubits, prefix='q'))


def square_virtual_device(control_r, num_qubits) -> PasqalVirtualDevice:
    return PasqalVirtualDevice(control_radius=control_r, qubits=TwoDQubit.square(num_qubits))


def test_init():
    d = generic_device(3)
    q0 = cirq.NamedQubit('q0')
    q1 = cirq.NamedQubit('q1')
    q2 = cirq.NamedQubit('q2')

    assert d.qubit_set() == {q0, q1, q2}
    assert d.qubit_list() == [q0, q1, q2]
    assert d.supported_qubit_type == (cirq.NamedQubit,)

    d = square_virtual_device(control_r=1.0, num_qubits=1)

    assert d.qubit_set() == {TwoDQubit(0, 0)}
    assert d.qubit_list() == [TwoDQubit(0, 0)]
    assert d.control_radius == 1.0
    assert d.supported_qubit_type == (
        ThreeDQubit,
        TwoDQubit,
        cirq.GridQubit,
        cirq.LineQubit,
    )


def test_init_errors():
    line = cirq.devices.LineQubit.range(3)
    with pytest.raises(TypeError, match="Unsupported qubit type"):
        PasqalDevice(qubits=line)
    with pytest.raises(ValueError, match="Too many qubits"):
        generic_device(101)

    with pytest.raises(TypeError, match="Unsupported qubit type"):
        PasqalVirtualDevice(control_radius=1.0, qubits=[cirq.NamedQubit('q0')])

    with pytest.raises(TypeError, match="All qubits must be of same type."):
        PasqalVirtualDevice(control_radius=1.0, qubits=[TwoDQubit(0, 0), cirq.GridQubit(1, 0)])

    with pytest.raises(ValueError, match="Control_radius needs to be a non-negative float"):
        square_virtual_device(control_r=-1.0, num_qubits=2)

    with pytest.raises(
        ValueError,
        match="Control_radius cannot be larger than "
        "3 times the minimal distance between qubits.",
    ):
        square_virtual_device(control_r=11.0, num_qubits=2)


def test_decompose_error():
    d = generic_device(2)
    op = (cirq.ops.CZ).on(*(d.qubit_list()))
    assert d.decompose_operation(op) == [op]

    op = op ** sympy.Symbol('exp')
    with pytest.raises(TypeError, match="Don't know how to work with "):
        d.decompose_operation(op)

    # MeasurementGate is not a GateOperation
    with pytest.raises(TypeError):
        d.decompose_operation(cirq.ops.MeasurementGate(num_qubits=2))
    # It has to be made into one
    assert d.is_pasqal_device_op(
        cirq.ops.GateOperation(
            cirq.ops.MeasurementGate(2), [cirq.NamedQubit('q0'), cirq.NamedQubit('q1')]
        )
    )


def test_is_pasqal_device_op():
    d = generic_device(2)

    with pytest.raises(ValueError, match="Got unknown operation"):
        d.is_pasqal_device_op(cirq.NamedQubit('q0'))

    op = (cirq.ops.CZ).on(*(d.qubit_list()))
    bad_op = cirq.ops.CNotPowGate(exponent=0.5)

    assert d.is_pasqal_device_op(op)
    assert d.is_pasqal_device_op(cirq.ops.X(cirq.NamedQubit('q0')))
    assert not d.is_pasqal_device_op(
        cirq.ops.CCX(cirq.NamedQubit('q0'), cirq.NamedQubit('q1'), cirq.NamedQubit('q2')) ** 0.2
    )
    assert not d.is_pasqal_device_op(bad_op(cirq.NamedQubit('q0'), cirq.NamedQubit('q1')))
    op1 = cirq.ops.CNotPowGate(exponent=1.0)
    assert d.is_pasqal_device_op(op1(cirq.NamedQubit('q0'), cirq.NamedQubit('q1')))

    op2 = (cirq.ops.H ** sympy.Symbol('exp')).on(d.qubit_list()[0])
    assert not d.is_pasqal_device_op(op2)

    decomp = d.decompose_operation(op2)
    for op_ in decomp:
        assert d.is_pasqal_device_op(op_)

    d2 = square_virtual_device(control_r=1.1, num_qubits=3)
    assert d.is_pasqal_device_op(cirq.ops.X(TwoDQubit(0, 0)))
    assert not d2.is_pasqal_device_op(op1(TwoDQubit(0, 0), TwoDQubit(0, 1)))


def test_decompose_operation():
    d = generic_device(3)
    for op in d.decompose_operation((cirq.CCZ ** 1.5).on(*(d.qubit_list()))):
        d.validate_operation(op)

    p_qubits = [cirq.LineQubit(3), cirq.LineQubit(4)]
    d = PasqalVirtualDevice(1.0, p_qubits)
    op = (cirq.ops.CNOT).on(*(d.qubit_list())) ** 2

    assert d.decompose_operation(op) == []


def test_pasqal_converter():
    q = cirq.NamedQubit.range(2, prefix='q')
    g = cirq.TwoQubitGate()

    class FakeOperation(cirq.ops.GateOperation):
        def __init__(self, gate, qubits):
            self._gate = gate
            self._qubits = qubits

        @property
        def qubits(self):
            return self._qubits

        def with_qubits(self, *new_qubits):
            return FakeOperation(self._gate, new_qubits)

    op = FakeOperation(g, q).with_qubits(*q)
    d = PasqalDevice(q)

    with pytest.raises(TypeError, match="Don't know how to work with"):
        d.decompose_operation(op)


def test_validate_operation_errors():
    d = generic_device(3)
    circuit = cirq.Circuit(device=d)

    with pytest.raises(ValueError, match="Unsupported operation"):
        d.validate_operation(cirq.NamedQubit('q0'))

    with pytest.raises(ValueError, match="is not a supported gate"):
        d.validate_operation((cirq.ops.H ** 0.2).on(cirq.NamedQubit('q0')))

    with pytest.raises(ValueError, match="is not a valid qubit for gate cirq.X"):
        d.validate_operation(cirq.X.on(cirq.LineQubit(0)))

    with pytest.raises(ValueError, match="is not part of the device."):
        d.validate_operation(cirq.X.on(cirq.NamedQubit('q6')))

    with pytest.raises(
        NotImplementedError, match="Measurements on Pasqal devices don't support invert_mask."
    ):
        circuit.append(cirq.measure(*d.qubits, invert_mask=(True, False, False)))

    d = square_virtual_device(control_r=1.0, num_qubits=3)
    with pytest.raises(ValueError, match="are too far away"):
        d.validate_operation(cirq.CZ.on(TwoDQubit(0, 0), TwoDQubit(2, 2)))


def test_validate_moment():
    d = square_virtual_device(control_r=1.0, num_qubits=2)
    m1 = cirq.Moment([cirq.Z.on(TwoDQubit(0, 0)), (cirq.X).on(TwoDQubit(1, 1))])
    m2 = cirq.Moment([cirq.Z.on(TwoDQubit(0, 0))])
    m3 = cirq.Moment([cirq.measure(TwoDQubit(0, 0)), cirq.measure(TwoDQubit(1, 1))])

    with pytest.raises(ValueError, match="Cannot do simultaneous gates"):
        d.validate_moment(m1)
    d.validate_moment(m2)
    d.validate_moment(m3)


def test_validate_circuit():
    d = generic_device(2)
    circuit1 = cirq.Circuit(device=d)
    circuit1.append(cirq.X(cirq.NamedQubit('q1')))
    circuit1.append(cirq.measure(cirq.NamedQubit('q1')))
    d.validate_circuit(circuit1)
    circuit1.append(cirq.CX(cirq.NamedQubit('q1'), cirq.NamedQubit('q0')))
    with pytest.raises(ValueError, match="Non-empty moment after measurement"):
        d.validate_circuit(circuit1)


def test_can_add_operation_into_moment():
    d = square_virtual_device(control_r=1.0, num_qubits=2)
    m1 = cirq.Moment([cirq.Z.on(TwoDQubit(0, 0))])
    assert not d.can_add_operation_into_moment(cirq.X.on(TwoDQubit(0, 0)), m1)
    assert not d.can_add_operation_into_moment(cirq.X.on(TwoDQubit(1, 1)), m1)
    m2 = cirq.Moment([cirq.measure(*d.qubits[:-1])])
    assert d.can_add_operation_into_moment(cirq.measure(TwoDQubit(1, 1)), m2)


def test_minimal_distance():
    dev = square_virtual_device(control_r=1.0, num_qubits=1)

    with pytest.raises(ValueError, match="Two qubits to compute a minimal distance."):
        dev.minimal_distance()

    dev = square_virtual_device(control_r=1.0, num_qubits=2)

    assert np.isclose(dev.minimal_distance(), 1.0)


def test_distance():
    dev = square_virtual_device(control_r=1.0, num_qubits=2)

    with pytest.raises(ValueError, match="Qubit not part of the device."):
        dev.distance(TwoDQubit(0, 0), TwoDQubit(2, 2))

    assert np.isclose(dev.distance(TwoDQubit(0, 0), TwoDQubit(1, 0)), 1.0)

    dev = PasqalVirtualDevice(control_radius=1.0, qubits=[cirq.LineQubit(0), cirq.LineQubit(1)])

    assert np.isclose(dev.distance(cirq.LineQubit(0), cirq.LineQubit(1)), 1.0)

    dev = PasqalVirtualDevice(
        control_radius=1.0, qubits=[cirq.GridQubit(0, 0), cirq.GridQubit(1, 0)]
    )

    assert np.isclose(dev.distance(cirq.GridQubit(0, 0), cirq.GridQubit(1, 0)), 1.0)


def test_value_equal():
    dev = PasqalDevice(qubits=[cirq.NamedQubit('q1')])

    assert PasqalDevice(qubits=[cirq.NamedQubit('q1')]) == dev

    dev = PasqalVirtualDevice(control_radius=1.0, qubits=[TwoDQubit(0, 0)])

    assert PasqalVirtualDevice(control_radius=1.0, qubits=[TwoDQubit(0, 0)]) == dev


def test_repr():
    assert repr(generic_device(1)) == ("pasqal.PasqalDevice(qubits=[cirq.NamedQubit('q0')])")
    dev = PasqalVirtualDevice(control_radius=1.0, qubits=[TwoDQubit(0, 0)])
    assert repr(dev) == (
        "pasqal.PasqalVirtualDevice(control_radius=1.0, qubits=[pasqal.TwoDQubit(0, 0)])"
    )


def test_to_json():
    dev = PasqalDevice(qubits=[cirq.NamedQubit('q4')])
    d = dev._json_dict_()
    assert d == {"cirq_type": "PasqalDevice", "qubits": [cirq.NamedQubit('q4')]}
    vdev = PasqalVirtualDevice(control_radius=2, qubits=[TwoDQubit(0, 0)])
    d = vdev._json_dict_()
    assert d == {
        "cirq_type": "PasqalVirtualDevice",
        "control_radius": 2,
        "qubits": [cirq.pasqal.TwoDQubit(0, 0)],
    }
