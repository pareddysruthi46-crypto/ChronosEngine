import pytest

from mmap_ringbuffer import MMapRingBuffer
from order_schema import ORDER_STRUCT


@pytest.fixture
def buffer(tmp_path):
    filename = str(tmp_path / "packed_test.dat")
    ring = MMapRingBuffer(filename, capacity=10)

    yield ring

    ring.close()


def make_record(order_id=1):
    return ORDER_STRUCT.pack(
        order_id,
        b"B",
        150.0,
        10,
        123456789,
    )


def test_push_packed_stores_record(buffer):
    buffer.push_packed(make_record())

    orders = buffer.read_all()

    assert len(orders) == 1
    assert orders[0]["order_id"] == 1


def test_push_packed_accepts_memoryview(buffer):
    buffer.push_packed(memoryview(make_record(2)))

    orders = buffer.read_all()

    assert len(orders) == 1
    assert orders[0]["order_id"] == 2


def test_push_packed_rejects_invalid_type(buffer):
    with pytest.raises(TypeError):
        buffer.push_packed("invalid")


def test_push_packed_rejects_wrong_record_size(buffer):
    with pytest.raises(ValueError):
        buffer.push_packed(b"short")


def test_push_packed_without_flush_and_explicit_flush(buffer):
    buffer.push_packed(make_record(3), flush=False)

    assert buffer.unread_count == 1

    buffer.flush()

    orders = buffer.read_all()

    assert len(orders) == 1
    assert orders[0]["order_id"] == 3


def test_push_packed_rejects_write_after_shutdown(buffer):
    assert buffer.shutdown(timeout=1.0)

    with pytest.raises(RuntimeError):
        buffer.push_packed(make_record(4))
