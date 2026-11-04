import pathlib
import sys
import unittest
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'sdk'))
from craftlink import CraftLinkError
from photocraft_readonly import PhotoCraftInspector, layer_objects


class LayerContractTests(unittest.TestCase):
    def test_duplicate_names_preserve_distinct_stable_ids_and_parent(self):
        document = uuid.uuid4()
        tree = dict(layers=[dict(id=1, name='same', kind='Group', children=[dict(id=2, name='same', kind='Pixel')])])
        first = layer_objects(document, tree)
        tree['layers'][0]['name'] = 'renamed'
        second = layer_objects(document, tree)
        self.assertEqual([o['object'] for o in first], [o['object'] for o in second])
        self.assertNotEqual(first[0]['object'], first[1]['object'])
        self.assertEqual(first[1]['parent'], first[0]['object'])
        self.assertNotEqual(first[0]['object'], layer_objects(uuid.uuid4(), tree)[0]['object'])

    def test_malformed_duplicate_and_deep_trees_fail_explicitly(self):
        layer = dict(id=1, name='fixture', kind='Pixel')
        for tree in [None, {}, dict(layers=[layer, layer]), dict(layers=[dict(layer, id=True)]),
                     dict(layers=[dict(layer, children={})])]:
            with self.subTest(tree=tree), self.assertRaises(CraftLinkError):
                layer_objects(uuid.uuid4(), tree)
        branch = dict(id=1, name='fixture', kind='Group')
        for native in range(2, 70):
            branch = dict(id=native, name='fixture', kind='Group', children=[branch])
        with self.assertRaises(CraftLinkError) as rejected:
            layer_objects(uuid.uuid4(), dict(layers=[branch]))
        self.assertEqual(rejected.exception.code, 'capability')

    def test_write_rejection_needs_no_native_connection(self):
        inspector = PhotoCraftInspector(1, 'unused-credential-file', uuid.uuid4())
        with self.assertRaises(CraftLinkError) as rejected:
            inspector.apply_changes(dict(name='unsupported'))
        self.assertEqual(rejected.exception.code, 'capability')
        self.assertFalse(inspector.manifest()['write'])


if __name__ == '__main__':
    unittest.main()
