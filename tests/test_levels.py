from vesuvius_data_explorer.volume import list_levels


class FakeArray:
    shape = (12, 20, 30)
    dtype = 'uint8'


class FakeGroup:
    attrs = {'multiscales': [{'datasets': [{'path': '0'}, {'path': '1'}]}]}

    def __getitem__(self, key):
        assert key in ['0', '1']
        return FakeArray()

    def array_keys(self):
        return ['0', '1']


def test_multiscale_metadata_discovery():
    assert [x.key for x in list_levels(FakeGroup())] == ['0', '1']
