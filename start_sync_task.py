import os
import signal
import subprocess
import time
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from threading import Event, Timer,Thread
import sdnotify
import argparse

class FolderSyncHandler(FileSystemEventHandler):
    """Logs all the events captured."""

    PERIODIC_SYNC_TIME=300
    DEBOUNCE_SYNC_TIME=30
    def __init__(self, remote_rclone_config,remote_sync_path,local_sync_path,logger=None,):
        super().__init__()
        self.logger = logger or logging.root
        
        
        self.remote_rclone_config = remote_rclone_config
        self.remote_sync_path = remote_sync_path
        self.local_sync_path = local_sync_path


        self.wait_period_before_actual_sync=self.DEBOUNCE_SYNC_TIME
        self.timed_sync_task = None
        
        #can daemon clean resource automatically, or just wait for rclone to finish?,no it cannot.
        self.period_update_thread = Thread(target=self.sync_periodically,args=(self.PERIODIC_SYNC_TIME,))
        self.period_update_thread.daemon = True
        self.period_update_thread.start()
    def cancel_sync_task(self):
        # if the sync job is already running, then we can just wait for it to be done
        if self.timed_sync_task is not None :
            self.logger.info("attempting to cancel the current sync task")
            self.timed_sync_task.cancel()
            self.timed_sync_task.join()
            self.logger.info("the old sync task is finished")


    def activate_sync_task(self):
        print("new sync task is queued in")
        self.cancel_sync_task()
        self.timed_sync_task = Timer(self.wait_period_before_actual_sync,self._call_rclone)
        self.timed_sync_task.daemon = True
        self.logger.info(f"wait for {self.wait_period_before_actual_sync} seconds to call rclone")
        self.timed_sync_task.start()
        

    def on_modified(self, event):
        super().on_modified(event)
        what = 'directory' if event.is_directory else 'file'
        self.logger.info("Modified %s: %s", what, event.src_path)
        if what == "file":
            return # a modification on file corresponds to 1 mod on directory, so only sync on directory change
        self.activate_sync_task()
        
    def sync_periodically(self,period):
        while True:
            time.sleep(period)
            self.activate_sync_task()

    
    def _call_rclone(self):
        notifier.notify("STATUS=syncing")
        
        
        #https://forum.rclone.org/t/how-to-speed-up-google-drive-sync/8444
        rclone_task = subprocess.Popen(["rclone", "bisync" ,f"{self.remote_rclone_config}:{self.remote_sync_path}",f"{self.local_sync_path}","--transfers=40","--checkers=40",
        "--tpslimit=300","--tpslimit-burst=100","--max-backlog=200000","--fast-list"],preexec_fn=os.setpgrp)
        return_code = rclone_task.wait()
        if return_code==2:
            notifier.notify("STATUS=critical failure")
            # self.logger.info(f"rclone failed, run with --resync again")
        elif return_code==0:
            notifier.notify("STATUS=success")
            self.logger.info(f"Synchronization successful")



global_exit_event = Event()
notifier = sdnotify.SystemdNotifier()


def handling_exit_signal(signum,_frame):
    global_exit_event.set()

if __name__ == "__main__":
    signal.signal(signal.SIGABRT,handling_exit_signal)
    signal.signal(signal.SIGTERM,handling_exit_signal)
    signal.signal(signal.SIGINT,handling_exit_signal)
    
    
    
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')

    parser = argparse.ArgumentParser()
    parser.add_argument("remote_rclone_config", help="the configuration name from rclone (See rclone config)")
    parser.add_argument("remote_sync_path", help="path of the drive folder you want to sync (relative to your root_folder in your rclone config)")
    parser.add_argument("local_sync_path", help="path of the local folder  you want to sync with drive")
    args = parser.parse_args()

    local_sync_path=args.local_sync_path
    remote_sync_path=args.remote_sync_path
    remote_rclone_config=args.remote_rclone_config



    event_handler = FolderSyncHandler(remote_rclone_config,remote_sync_path,local_sync_path)
    observer = Observer()
    observer.schedule(event_handler, local_sync_path, recursive=True)
    observer.start()
    notifier.notify("READY=1")
    try:
        while not global_exit_event.is_set():
            global_exit_event.wait(10)
    finally:
        print("tying up all loose ends")
        notifier.notify("STOPPING=1")
        event_handler.cancel_sync_task()
        observer.stop()
        observer.join()