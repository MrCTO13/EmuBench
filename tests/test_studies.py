import unittest
import uuid
from emubench import adapters, catalog, lab

class Studies(unittest.TestCase):
    def test_shortlist_and_frozen_sample(self):
        self.assertEqual(set(adapters.NAMES)-{"cartssnes"}, {k for k,v in catalog.CATALOG.items() if v.core})
        for study in lab.studies():
            self.assertEqual([len(g["games"]) for g in study["groups"]],[6]*4)
            self.assertEqual(len({g["edition"] for group in study["groups"] for g in group["games"]}),24)
    def test_missing_duplicate_and_extra_private_fields(self):
        s=lab.studies()[0]
        host={"os":"Darwin","arch":"arm64","cpu":"Test CPU","device":str(uuid.uuid4()),"worker_sha256":"c"*64}
        builds={"Snes9x":"a"*64,"bsnes":"b"*64}
        rows=[dict(edition=g["edition"],emulator=p,version="1.0",average_fps=50,low_1pct_fps=30,
                   high_1pct_fps=70,run_id=str(uuid.uuid4())) for group in s["groups"] for g in group["games"] for p in builds]
        r=dict(study=s["id"],campaign=str(uuid.uuid4()),host=host,gate="dedicated",builds=builds,rows=rows)
        lab.validate_receipt([s],r)
        for bad in (rows[:-1],rows[:-1]+[rows[0]],[{**rows[0],"path":"private"},*rows[1:]]):
            with self.assertRaises(ValueError):
                lab.validate_receipt([s],{**r,"rows":bad})
        plan={"study":s["id"],"dedicated":True,"cores":{"snes9x":{"sha256":"a"*64},"bsnes":{"sha256":"b"*64}}}
        with self.assertRaisesRegex(ValueError,"48 required"):
            lab.review(s,plan,[])
        with self.assertRaisesRegex(ValueError,"failed"):
            lab.review(s,plan,[("held",3,None)])
