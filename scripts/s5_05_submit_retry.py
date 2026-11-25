from pathlib import Path
import s5_05_submit as s
from catalyst_ai.workbench import backup
b=s.R/'backups/s5-05-m3-20261124-v2';s.freeze();b.mkdir(parents=True,exist_ok=False);backup.backup_database(s.DB,b/'before.sqlite');backup.backup_database(b/'before.sqlite',b/'rehearsal.sqlite');print('rehearsal',s.submit(b/'rehearsal.sqlite'),flush=True);print('formal',s.submit(s.DB),flush=True)
