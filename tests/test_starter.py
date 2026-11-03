import hashlib,json,os
from pathlib import Path
import shutil,subprocess,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
class StarterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'starter'
        shutil.copytree(ROOT,self.root,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.git'))
    def test_entrypoint_exists(self):
        self.assertTrue((ROOT/'audit.py').is_file(),'Starter entry point is missing')
    def test_demo_reproduces_all_original_reports(self):
        folder=self.root/'examples/fictional-workflow/reports'
        before={p.relative_to(folder):p.read_bytes() for p in folder.rglob('*') if p.is_file()}
        self.assertEqual(len(before),17)
        shutil.rmtree(folder)
        p=subprocess.run([sys.executable,'audit.py','demo'],cwd=self.root,capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        after={p.relative_to(folder):p.read_bytes() for p in folder.rglob('*') if p.is_file()}
        self.assertEqual(before,after)
    def test_live_rejects_private_url_without_touching_demo(self):
        path=self.root/'examples/fictional-workflow/reports/discoverability/report.json'
        before=path.read_bytes()
        p=subprocess.run([sys.executable,'audit.py','live','http://127.0.0.1/'],cwd=self.root,capture_output=True,text=True)
        self.assertEqual(p.returncode,2,p.stderr)
        self.assertIn('Destination IP',p.stderr)
        self.assertFalse((self.root/'reports').exists())
        self.assertEqual(before,path.read_bytes())
    def test_live_cannot_write_into_frozen_example(self):
        p=subprocess.run([sys.executable,'audit.py','live','https://example.org/','--output-dir','examples/fictional-workflow/reports'],cwd=self.root,capture_output=True,text=True)
        self.assertEqual(p.returncode,2,p.stderr)
        self.assertIn('reports/',p.stderr)
    def test_live_cannot_escape_or_use_symlink(self):
        (self.root/'reports').symlink_to(self.root,target_is_directory=True)
        p=subprocess.run([sys.executable,'audit.py','live','https://example.org/'],cwd=self.root,capture_output=True,text=True)
        self.assertEqual(p.returncode,2)
        self.assertIn('symlink',p.stderr)
if __name__=='__main__':unittest.main()
