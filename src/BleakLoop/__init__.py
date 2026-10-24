def create_instance(c_instance):
    from .surface import BleakLoop

    return BleakLoop(c_instance=c_instance)
