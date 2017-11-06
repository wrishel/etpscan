#!/usr/bin/env python

import pygtk
import gobject
import subprocess
pygtk.require('2.0')
import gtk
import os
import os.path
import signal
import argparse
import logging

import pdb

# Instead of multiprocessing, which may be conflicting with gtk,
# let's register the analysis process as a timeout based poll under gtk
import Queue as Queue2
from multiprocessing import Queue

from time import sleep

def intval_or_0(x):
    try:
        r = int(x)
    except ValueError:
        r = 0
    return r;

class ScanControl:

    # Called when any key is pressed and focus is in who entry area
    def whokey(self, widget, data=None):
        print "whokey"
        print data
    
    # Called when scan button is activated, invokes scanimage in batch
    def scan(self, widget, data=None):
        """Start nautilus, call out to scanimage, register timeout."""
        next_to_scan = self.find_highwater()
        next_to_scan += 1
        self.scan_start = next_to_scan
        self.nautilus = subprocess.Popen(["nautilus",self.dir])
        popen_args = [
            "/usr/local/bin/scanimage",
            "--mode",
            "color", 
            "--buffer-size",
            "--source",
            "ADF Duplex",
            "--compression",
            "JPEG",
            "--batch=%s/%%06d.jpg" % (self.dir,),
            "-y",
            "357", #433 mm = 17", 383=15", 280 = 11", 357 = 14"
            "--page-height",
            "357", #433 mm = 17", 383=15"
            "--resolution",
            "%d" % (self.dpi,),
            "--batch-start",
            "%d" % (next_to_scan,)] 
        if self.endorser:
            popen_args.append("--endorser=yes")
            popen_args.append("--endorser-bits")
            popen_args.append("24")
            popen_args.append("--endorser-val")
            popen_args.append("%d" % (next_to_scan,))
            popen_args.append("--endorser-step")
            popen_args.append("2")
	    popen_args.append("--endorser-string")
	    popen_args.append("%08ud")
            popen_args.append("--endorser-y")
            popen_args.append("165") # beneath the barcode
        self.p = subprocess.Popen(popen_args)
        self.to = gobject.timeout_add(500,self.timeoutfunc)


    def find_highwater(self):
        print self.dir
        dirlist = os.listdir(self.dir)
        namelist = [i.split(".")[0] for i in dirlist]
        intlist = [intval_or_0(i) for i in namelist]
        try:
            self.highwater = max(intlist)
        except ValueError:
            self.highwater = -1
        #print "Highest file number in %s is %d" % (self.dir,self.highwater)
        return self.highwater

    def timeoutfunc(self):
        return_code = self.p.poll()
        new_label = ""
        if return_code is not None: 
            print "Done: Returned code", return_code
            scan_count = self.find_highwater() - self.scan_start
            scan_count = scan_count + 1
            if scan_count > 0:
                new_label = "Scanned from %d to %d (%d sides or %d pages) pct %s by %s" % (self.scan_start,self.highwater,scan_count,(scan_count/2),self.pct_entry.get_text(),self.who_entry.get_text())
                self.results.set_text(new_label)
                # create marker file for highwater
                highnum = self.scan_start + scan_count - 1
                highname = os.path.join(self.dir,"%06d.marker" % highnum)
		open(highname,'w').close()
                # fnum represents new file, move each to appropriate dir
                for fnum in range(self.scan_start, 
                                  self.scan_start + scan_count):
                    #self.dir includes incoming
                    fname = "%06d.jpg" % fnum
                    fromname = os.path.join(self.dir,fname)
                    toname = os.path.join(self.root,
                                          "%03d" % (fnum/1000),
                                          fname)
                    try:
                        print "Moving ", fromname, " to ", toname
                        os.renames(fromname,toname)
                    except Exception as e:
                        print e
            else:
                self.results.set_text("None scanned.")
            #print new_label
            logging.info(new_label)
            # We are done scanning, and should 
            # 1) create a marker file for the next highwater
            # 2) move all scan files starting with number
            #    self.scan_start through that plus scan_count
            #    TO the appropriate thousands directory
            #    FROM incoming.
            # We can then queue up all those files for further
            # processing, in the event we have multiprocessing.
            # (Note we only need to process fronts...)
            return False
        else:
            self.results.set_text("Scanning...")
            # We are still scanning, but can perhaps fire up
            # a process to 
            try:
                data = self.data_queue.get_nowait()
            except Queue2.Empty:
                pass
            # now deal with the returned data, if any
            return True
        

    def delete_event(self, widget, event, data=None):
        # If you return FALSE in the "delete_event" signal handler,
        # GTK will emit the "destroy" signal. Returning TRUE means
        # you don't want the window to be destroyed.
        # This is useful for popping up 'are you sure you want to quit?'
        # type dialogs.
        # Change FALSE to TRUE and the main window will not be destroyed
        # with a "delete_event".
        return False

    def destroy(self, widget, data=None):
        gtk.main_quit()

    def __init__(self, rootdir, incomingdir, dpi, endorser=True):
        # create q
        self.data_queue = Queue()

        # create window for gui

        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        # store directory to which files will be saved
        self.root = rootdir
        self.dir = incomingdir
        self.dpi = dpi
        self.endorser = endorser
        self.scan_start = 0
        self.nautilus = None
        self.window.connect("delete_event", self.delete_event)
        self.window.connect("destroy", self.destroy)
        self.window.set_border_width(10)
        self.window.move(300,300)
    
        # We have a button to start scanimage, a button to exit,
        # and some labeled text widgets to capture user info.
        self.box0 = gtk.VBox(False,0)
        self.box1 = gtk.HBox(False,0)
        self.pct_label = gtk.Label("Precinct:")
        self.pct_entry = gtk.Entry()
        self.who_label = gtk.Label("Staff:")
        self.who_entry = gtk.Entry()
        self.scan_button = gtk.Button("Scan")
        self.box0.pack_start(self.box1,True,True,0)
        self.results = gtk.Label("Results")
        self.box0.pack_start(self.results,True,True,0)
        self.box1.pack_start(self.pct_label,True,True,0)
        self.box1.pack_start(self.pct_entry,True,True,0)
        self.box1.pack_start(self.who_label,True,True,0)
        self.box1.pack_start(self.who_entry,True,True,0)
        self.box1.pack_start(self.scan_button,True,True,0)
        self.exit_button = gtk.Button("Exit")
        self.box1.pack_start(self.exit_button,True,True,0)
        self.scan_button.connect("clicked", self.scan, None)
	# key_press and keypress keypressed are wrong event names; KeyPress?
	# key-event and key_event and keypress-event and keydown-event are wrong
        self.who_entry.connect("activate", self.scan, None)
        self.exit_button.connect_object("clicked", 
                                        gtk.Widget.destroy, 
                                        self.window)

        # This packs the button into the window (a GTK container).
        self.window.add(self.box0)
    
        # The final step is to display this newly created widget.
        self.box0.show()
        self.results.show()
        self.box1.show()
        self.pct_label.show()
        self.pct_entry.show()
        self.who_label.show()
        self.who_entry.show()
        self.scan_button.show()
        self.exit_button.show()
    
        # and the window
        self.window.show()

    def main(self):
        # All PyGTK applications must have a gtk.main(). Control ends here
        # and waits for an event to occur (like a key press or mouse event).
        gtk.main()

# If the program is run directly or passed as an argument to the python
# interpreter then create a ScanControl instance and show it
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Scan some stuff.')
    parser.add_argument('--dir',nargs=1,default='/tmp')
    parser.add_argument('--dpi',nargs=1,default=300,type=int)
    x=parser.parse_args()#"--dir /home/tevs".split())
    # ensure the specified directory exists with an incoming subdir and 000 through 099 subdirs
    try:
        os.mkdir(x.dir[0])
    except OSError:
        pass
        #print "%s already exists" % (x.dir[0],)
    try:
        os.mkdir(x.dir[0]+'/incoming')
    except OSError:
        pass#print "%s/incoming already exists" % (x.dir[0],)
    for num in range(199):
        try:
            os.mkdir("%s/%03d" % (x.dir[0],num))
            print "%s/%03d created " % (x.dir[0],num)
        except OSError:
            print "%s/%03d already exists" % (x.dir[0],num)
    # get the highest number used in a file name in the incoming dir
    # increment it and use it as the initial file number for scanning

    # pass incoming directory to the scanning routines as their write dir
    # pass incoming dpi to the scanning routines
    logging.basicConfig(filename="/home/tevs/scanlog.txt",
                        format='%(asctime)s %(message)s',
                        level=logging.DEBUG)
    scan_control = ScanControl(x.dir[0], #rootdir
                               os.path.join(x.dir[0],"incoming"), #incomingdir
                               x.dpi[0]) #dpi
    scan_control.main()
