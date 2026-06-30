import subprocess
def is_synced(runner=subprocess.run) -> bool:
    r = runner(["timedatectl","show","-p","NTPSynchronized","--value"], capture_output=True, text=True)
    return r.stdout.strip() == "yes"
