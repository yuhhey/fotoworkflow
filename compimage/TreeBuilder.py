#-*- coding: utf-8 -*-9

import wx
import wx.gizmos
import os
import errno
import CompositeImage
import copy
import threading as TH
import time
import glob
import pickle
import locale
import signal
import subprocess

locale.setlocale(locale.LC_ALL, "")


class Command(object):
    def __init__(self):
        self._want_abort = 0
        
    def abort(self):    
        self._want_abort = 1
        
    def abortWanted(self):
        return self._want_abort != 0
    
    def __call__(self):
        print "Command object default operation: sleep for 5 sec"
        time.sleep(5)
    
        
class NullCommand(Command):
    def __call__(self, *args, **kwargs):
        pass
    
    
class SeqParserCommand(Command):
    def __init__(self, path):
        super(SeqParserCommand, self).__init__()
        self.path = path
        
    def __call__(self):
        config = seq_config_dict[self.path]
        try: 
            collect_seq_strategy = CompositeImage.CollectSeqStrategy()
            hdrs, single_imgs = collect_seq_strategy.parseDir(self.path,
                                                              config)
            # TODO: Még a HDR-eket nem vizsgálja
            target_dir = config.GetTargetDir()
            pano_config = CompositeImage.PanoWeakConfig(target_dir, 25)
            panos, single_imgs = collect_seq_strategy.parseIMGList(single_imgs,
                                                                   pano_config)
            return (hdrs, panos, single_imgs)
        except IOError:  # handling the case when there are no raw files
            print "No RAW input to parse in %s" % self.path    


class SeqGenCommand(Command):
    def __init__(self, seq, config, gen):
        super(SeqGenCommand, self).__init__()
        self.seq = seq
        self.gen = gen
        self.config = config
        
    def __call__(self):
        return self.gen(self.seq, self.config)


wxEVT_COMMAND_UPDATE = wx.NewEventType()
EVT_COMMAND_UPDATE = wx.PyEventBinder(wxEVT_COMMAND_UPDATE, 1)


class CommandUpdate(wx.PyCommandEvent):
    def __init__(self, callback):
        super(CommandUpdate, self).__init__(wxEVT_COMMAND_UPDATE, 0)
        # Attributes
        self.value = None
        self.callback = callback
        self.result = 'Failed'
        self.task_id = None
        
    def SetValue(self, value):
        self.value = value
        
    def GetValue(self):
        return self.value

    def SetTaskID(self, task_id):
        self.task_id = task_id
        
    def GetTaskID(self):
        return self.task_id

    def SetThreadID(self, th_id):
        self.th_id = th_id
        
    def GetThreadID(self):
        return self.th_id


class WorkerThread(TH.Thread):
    """Worker Thread Class."""
    def __init__(self, cmd, task_id, notify_window, callback):
        """Init Worker Thread Class."""
        super(WorkerThread, self).__init__()
        self._cmd = cmd
        self.task_id = task_id
        self._notify_window = notify_window
        self.callback = callback
        self.start()

    def run(self):
        """Run Worker Thread."""
        event = CommandUpdate(self.callback)
        result = self._cmd()
        if result != None:
            event.result = 'Ok'
        event.SetValue(result)
        event.SetTaskID(self.task_id)
        event.SetThreadID(self)
        wx.PostEvent(self._notify_window, event)
        
    def abort(self):
        self._cmd.abort()


class ExpanderPopup(wx.Menu):
    def __init__(self):
        super(ExpanderPopup, self).__init__()

    def AddItem(self, label, callback):
        item = wx.MenuItem(self, wx.NewId(), label)
        self.AppendItem(item)
        self.Bind(wx.EVT_MENU, callback, item)
        return item
    
    def AddMenuItems(self, items):
        for l, c in items: 
            self.AddItem(l, c)    

    
class Expander(object):
    # TODO: menu item kezelés az ImageSequenceExpanderPopup-ból.
    def __init__(self, tree, itemID):
        
        self.tree = tree
        self.itemID = itemID
        self.tree.SetPyData(itemID, self)
        self.expanded = False
        self.tree.SetType(itemID, self.type_string)
        config_key = self.ConfigKey()
        if config_key:
            self.tree.UpdateConfig(self.itemID, seq_config_dict[config_key])
        else: # Expanders without config return None
            pass
        
    def isExpanded(self):
        raise NotImplementedError
                            
    def expand(self, *args, **kwargs):
        pass
        #raise NotImplementedError
    
    def GetPopupMenu(self, *args, **kwargs):
        raise NotImplementedError
    
    # TODO: megfontolandó, hogy ez különálló függvény legyen - e egy plusz tree paraméterrel

    def handleClick(self):
        raise NotImplementedError
    
    def WalkChildren(self):
        child, cookie = self.tree.GetFirstChild(self.itemID)
        while child.IsOk():
            yield child
            child, cookie = self.tree.GetNextChild(self.itemID, cookie)
    
    def ResetLabel(self):
        pass
    
    # kellene egy iterator, ami az expander közvetlen childrenjein iterál
    def DestroyChildren(self):
        for child in self.WalkChildren():
            expander = self.tree.GetPyData(child)
            expander.DestroyChildren()
            key = expander.ConfigKey()
            if key:
                del seq_config_dict[key]
            del expander
            
        self.tree.DeleteChildren(self.itemID)
        self.expanded = False
        self.ResetLabel()
        
    #Nem kell
    def hasChildWithType(self, t):
        """ Checks if a child with the given type 't' exists"""
        return self.itemHasChildOfType(self.itemID, t)
    
    # TODO: megfontolandó, hogy ez különálló függvény legyen - e egy plusz tree paraméterrel

    def findType(self, item, t):
        if item.IsOk():
            pt = self.itemHasChildOfType(item, t)
            if pt == None:
                return self.findType(self.tree.GetItemParent(item), t)
            return pt
        else:
            return None
    
    #Nem kell
    def findTypeAbove(self, t):
        """Checks if a child in higher level in the tree of type 't' exists"""
        p = self.tree.GetItemParent(self.itemID)
        return self.findType(p, t)
        
    def executeGen(self, dummyarg):
        pass
    
    def ConfigKey(self):
        return self.path

        
class DirectoryExpanderPopup(ExpanderPopup):
    def __init__(self, d_expander):
        super(DirectoryExpanderPopup, self).__init__()
        self.dir_expander = d_expander
        
        menu_items = [("HDR config", self.onHDRConf),
                      ("Panorama config", self.onPanoramaConf),
                      ("Symlinks", self.onSymlinks),
                      ("Generate recursively", self.onGen),
                      ("(Re)parse directory", self.onReparse)]
        
        self.AddMenuItems(menu_items)
        
    def onHDRConf(self, evt):
        print evt, type(evt)
        raise NotImplementedError  
        
    def onPanoramaConf(self, evt):
        raise NotImplementedError

    def ExecCmd(self, cmd):
        # TODO: First execute nullcommand, then the symlink generation.
        #      A command queue to be implemented in TreeWithImages
        
        self.dir_expander.ExecCmd(cmd)
    
    def onSymlinks(self, evt):    
        self.ExecCmd(CompositeImage.SymlinkGenerator())
        
    def onGen(self,evt):
        self.dir_expander.ExecCmd(None)

    def onReparse(self, evt):
        self.dir_expander.DestroyChildren()
        self.dir_expander.expand()
        
        
def GlobStarFilter(path):
    return [os.path.basename(d) for d in glob.glob(os.path.join(path, '*'))]


class DirectoryExpander(Expander):
    type_string = 'Dir'
    def __init__(self, tree, path, itemID):
        #FIXME: turn it to assert
        if not os.path.isdir(path):
            raise OSError(errno.ENOENT, os.strerror(errno.ENOENT))
        self.path = path
        
        tree.SetItemHasChildren(itemID)
        super(DirectoryExpander, self).__init__(tree, itemID)
        
    def isExpanded(self):
        return self.expanded
 
    def addSubdirsToTree(self, l):
        for fn in sorted(l, cmp=locale.strcoll):
            fullpath = os.path.join(self.path, fn)
            if os.path.isdir(fullpath):
                child = self.tree.AppendItem(self.itemID, fn)
                DirectoryExpander(self.tree, fullpath, child)
                      
    def UpdateItemText(self, text):
        item_text = self.tree.GetItemText(self.itemID)
        item_text = item_text + text
        self.tree.SetItemText(self.itemID, item_text)

    def AddSeqsItems(self, seqs, seq_expander_cls, seq_postfix):
        if len(seqs) == 0:
            return
        # Itt kihasznaljuk, hogy az osszes seq egy konyvtarbol van.
        path_config = seq_config_dict[self.path]
        seq_config = copy.deepcopy(path_config)
        seq_config.SetPrefix(seq_config.GetPrefix() + seq_postfix)

        prefix = seq_config.ExpandPrefix(seqs[0].getFilelist()[0])
        seq_path = seq_config.GetTargetDir()
        for fn, seq in enumerate(reversed(seqs)):
            actual_prefix = prefix + "_%d" % fn #seq_config.GetIndex()
            target_path = os.path.join(seq_path, actual_prefix)
            child = self.tree.AppendItem(self.itemID, target_path)
            seq_expander = seq_expander_cls(self.tree, self.path, target_path, child, seq)
            seq_config_per_image = copy.deepcopy(seq_config)
            seq_config_per_image.SetPrefix(actual_prefix)
            seq_config_dict[seq_expander.ConfigKey()] = seq_config_per_image

    def SeqParsedCallback(self, (hdrs, panos, single_images)):
        self.tree.clearState(self.itemID)
        
        n_hdrs = len(hdrs)
        
        n_panos = len(panos)
         
        text = "(%d hdrs, %d panos)" % (n_hdrs, n_panos)
        self.UpdateItemText(text)
        
        #if n_hdrs == 0:
        #    return
        
        self.AddSeqsItems(hdrs, HDRExpander, '_HDR')
        self.AddSeqsItems(panos, PanoExpander, '_PANO')

    def expand(self, f=GlobStarFilter):
        if self.isExpanded():   
            return
                
        l = f(self.path)
        self.addSubdirsToTree(l)
        cmd = SeqParserCommand(self.path)
        self.SeqParsedCallback(cmd())        
        self.expanded = True
 
    def GetPopupMenu(self):
        return DirectoryExpanderPopup(self)

    def ConfigKey(self):
        return self.path
    
    def handleClick(self):
        pass

    def ResetLabel(self):
        self.tree.SetItemText(self.itemID, os.path.basename(self.path))

    def executeGen(self,gen):
        return self.expand()
     
    def ExecCmd(self, cmd):
        self.tree.executeGen(cmd, self.itemID)
        

class RootItemExpanderPopup(DirectoryExpanderPopup):
    def __init__(self, d_expander):
        super(RootItemExpanderPopup, self).__init__(d_expander)
        
        root_menu_items = [("Change root", self.onChangeRoot)]
        
        self.AddMenuItems(root_menu_items)
    
    def onChangeRoot(self, evt):
        dlg = wx.DirDialog(parent=None)
        if wx.ID_OK == dlg.ShowModal():
            path = dlg.GetPath()
            tree = self.dir_expander.tree
            tree.DeleteAllItems()
            RootItemExpander(tree, path)
        dlg.Destroy()
        return None
        

class RootItemExpander(DirectoryExpander):
    def __init__(self, tree	, path):
        itemID = tree.AddRoot(path)
        super(RootItemExpander, self).__init__(tree, path, itemID)
        
    def GetPopupMenu(self):
        return RootItemExpanderPopup(self)

    def ResetLabel(self):
        pass


class ImageExpander(Expander):
    type_string = 'img'
    def __init__(self, tree, itemID, image):
        super(ImageExpander, self).__init__(tree, itemID)
        self.image = image

    #Image items have no children
    def DestroyChildren(self):
        pass
    
    def ConfigKey(self):
        return None


class ImageSequenceExpanderPopup(ExpanderPopup):
    
    #TODO: Megnézni, hogy nem elég-e az expander.executeGen függvényt átadni paraméterként.
    def __init__(self, expander):
        super(ImageSequenceExpanderPopup, self).__init__()
        self.expander = expander
        menu_items = [("Generate", self.onGenerate),
                      ("Symlinks", self.onCreateSymlink)]
        self.AddMenuItems(menu_items)
   
    def onGenerate(self, evt):
        self.expander.executeGen(gen=None)
        
    def onCreateSymlink(self,evt):
        self.expander.executeGen(CompositeImage.SymlinkGenerator())
                      

class ImageSequenceExpander(Expander):
    def __init__(self, tree, source_path, target_path, itemID, img_seq):
        self.target_path = target_path
        self.source_path = source_path
        self.seq = img_seq
        if len(self.seq) > 0:
            tree.SetItemHasChildren(itemID)
        super(ImageSequenceExpander, self).__init__(tree, itemID)
     
    def isExpanded(self):
        return self.expanded
    
    def expand(self, f=None):
        if self.isExpanded():
            return
        for img in sorted(self.seq):
            child = self.tree.AppendItem(self.itemID, os.path.basename(img))
            ImageExpander(self.tree, child, self.seq[img])
        self.expanded = True

    def handleClick(self):
        pass
        
    def GetPopupMenu(self):
        return ImageSequenceExpanderPopup(self)

    def ExecuteGenCallback(self, result):
        pass
    def _ConfigKey(self, s):
        if self.target_path[0] == '/': # os.path.join discards anything if an absolute path appears in the parameter list
            target_path_start = 1
        else:
            target_path_start = 0
        return os.path.join(self.source_path, s, self.target_path[target_path_start:])
    
    def ConfigKey(self):
        return self.target_path
    
    def _ExecCmd(self, gen):
        config = seq_config_dict[self.ConfigKey()]
        cmd = SeqGenCommand(self.seq, config, gen)
        task_id = self.tree.processingStarted(self.itemID)
        WorkerThread(cmd, task_id, self.tree, None)
        return task_id

    
class HDRExpander(ImageSequenceExpander):
    type_string = 'HDR'
    def executeGen(self, gen):
        if gen == None:
            gen = CompositeImage.HDRGenerator()
            
        task_id = self._ExecCmd(gen)
        return task_id

    def ConfigKey(self):
        return self._ConfigKey('HDR')


class PanoExpander(ImageSequenceExpander):
    type_string = 'Pano'
    def executeGen(self, gen):
        if gen == None:
            gen = CompositeImage.PanoGenerator()
            
        task_id = self._ExecCmd(gen)
        return task_id

    def ConfigKey(self):
        return self._ConfigKey('PANO')

    
class TreeDict(object):
    """ A dictionary which assumes keys are directory paths. It looks up
        elements with key up in the path"""
    def __init__(self):
        self.d = {}
                
    def __getitem__(self, key):
        k = os.path.abspath(key)
        if not k in self:
            d = os.path.dirname(k)
            if d == k:
                raise KeyError
            return self.__getitem__(d)
        
        return self.d[k]

    def __setitem__(self, key, value):
        key = os.path.abspath(key)
        self.d[key] = value

    def __delitem__(self, key):
        key = os.path.abspath(key)
        if key in self.d.keys():
            del self.d[key]
                
    def __len__(self):
        return len(self.d)


    def __contains__(self, key):
        return key in self.d.keys()

    def keys(self):
        return self.d.keys()
     

class TreeCtrlWithImages(wx.gizmos.TreeListCtrl):
    columns = [("Tree", 200, False),
               ("Type", 50, False),
               ("Target dir", 200, True),
               ("Raw ext", 60, True),
               ("Img ext", 60, True),
               ("Output prefix", 50, True),
               ("Maxdiff", 70, True),
               ("Checkers", 150, True)]
    def __init__(self, *args, **kwrds):
        
        super(TreeCtrlWithImages, self).__init__(*args, **kwrds)
        
        
        for i, (label, w, editable) in enumerate(self.columns):
            self.AddColumn(label, width=w)
            self.SetColumnEditable(i, editable)
        
        self.Bind(wx.EVT_TREE_END_LABEL_EDIT, self.OnEndLabelEdit)
        self.Bind(wx.EVT_TREE_BEGIN_LABEL_EDIT, self.OnBeginLabelEdit)
        # bitmaps for progress indication.
        self.il = wx.ImageList(16,16)
        self.AssignImageList(self.il)
        self.img_null = self.il.Add(wx.NullBitmap)
        self.imgs_wip = [self.il.Add(wx.Bitmap(fn)) for fn in sorted(glob.glob('roller_16-?.png'))]
        self.img_ready = self.il.Add(wx.ArtProvider.GetBitmap(wx.ART_TICK_MARK, wx.ART_OTHER, (16,16)))
        self.img_aborted = self.il.Add(wx.ArtProvider.GetBitmap(wx.ART_ERROR, wx.ART_OTHER, (16,16)))
        
        # Init for process accounting
        self.processedItems = {}
        self.process_idx = 0
        
        # Init for progress animation
        self.progressImageIndex = 0
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.updateProgress, self.timer)
        self.iterator = None
        self._cancel_wanted = False

    def OnBeginLabelEdit(self, evt):
        item=evt.GetItem()
        print item, evt.GetInt()
        expander = self.GetPyData(item)
        if expander.ConfigKey(): #Check if there is config for this item
            self.oszlop = evt.GetInt()
        else:
            evt.Veto()
            return

    config_methods = [CompositeImage.Config.SetTargetDir,
                      CompositeImage.Config.SetRawExt,
                      CompositeImage.Config.SetImageExt,
                      CompositeImage.Config.SetPrefix]

    def OnEndLabelEdit(self, evt):
        item=evt.GetItem()
        expander = self.GetPyData(item) 
        new_value = evt.GetLabel()
        config = seq_config_dict[expander.ConfigKey()]
        method_idx = self.oszlop-2
        self.config_methods[method_idx](config, new_value)
        seq_config_dict[expander.ConfigKey()] = config

    def processingStarted(self, item):
        if item in self.processedItems:
            raise TypeError # TODO ehelyett value error kellene
        self.process_idx = self.process_idx + 1
        self.processedItems[self.process_idx] = item
        #self.SetItemImage(item, self.imgs_wip[0],wx.TreeItemIcon_Normal)
        self.timer.Start(100) #in milliseconds
        return self.process_idx
        
    def updateProgress(self,e):
        self.progressImageIndex = (self.progressImageIndex + 1) % len(self.imgs_wip)
        for k in self.processedItems.keys():
            item = self.processedItems[k]
            self.SetItemImage(item, self.imgs_wip[self.progressImageIndex], wx.TreeItemIcon_Normal)
            
    def processingCompleted(self, task_id):
        self.SetItemImage(self.processedItems[task_id], self.img_ready,wx.TreeItemIcon_Normal)
        del self.processedItems[task_id]
        if self.isItemProcessed():
            return
        self.timer.Stop()
        
    def isItemProcessed(self):
        return not len(self.processedItems) == 0
        
    def processingFailed(self, task_id):
        item = self.processedItems[task_id]
        self.SetItemImage(item, self.img_aborted,wx.TreeItemIcon_Normal)
        del self.processedItems[task_id]
        if not self.isItemProcessed():
            self.timer.Stop()
        
    def clearState(self, item):
        self.SetItemImage(item, self.img_null, wx.TreeItemIcon_Normal)

    def executeGen(self, gen, itemID):
        if self.iterator:
            wx.MessageBox(message='One command is already being executed. Command added to queue')
            self.gen_list.append((gen, 4))
            return
        self.iterator = treeIterator(self, itemID)
        self.itemID = itemID
        self._cancel_wanted = False
        
        self.gen = NullCommand()
        self.max_thread = 2
        self.gen_list = [(gen, 4)]
              
    def executeNext(self):
        if self._cancel_wanted or self.iterator == None:
            return
        try:
            if TH.activeCount() < self.max_thread:
                item = self.iterator.next()
                expander = self.GetPyData(item)
                expander.executeGen(self.gen)
        except StopIteration:
            
            if len(self.gen_list) > 0:
                self.gen = self.gen_list[0][0]
                self.max_thread = self.gen_list[0][1]
                del self.gen_list[0]
                self.iterator = treeIterator(self, self.itemID)
            else:
                self.iterator = None
        
    def StopCommand(self):
        self._cancel_wanted=True
        self.iterator = None

    def UpdateConfig(self, item, config):
        self.SetItemText(item, config.GetTargetDir(), 2)
        self.SetItemText(item, config.GetRawExt(), 3)
        self.SetItemText(item, config.GetImageExt(), 4)
        self.SetItemText(item, config.GetPrefix(), 5)
        
    def SetType(self, item, t):
        self.SetItemText(item, t, 1)


class TreeCtrlFrame(wx.Frame):
    
    def __init__(self, parent, id, title, rootdir):
        super(TreeCtrlFrame, self).__init__(parent, id, title, wx.DefaultPosition, wx.Size(450, 350))
        panel = wx.Panel(self, -1)
        self.tree = TreeCtrlWithImages(panel, 1, wx.DefaultPosition, (-1,-1), wx.TR_HAS_BUTTONS)
        
        self.config_key = rootdir
        
        seq_config_dict[rootdir] = CompositeImage.HDRConfig('/tmp')
        RootItemExpander(self.tree, rootdir)
        
        self.updatebutton = wx.Button(self, id=wx.ID_REFRESH)
        self.updatebutton.Bind(wx.EVT_BUTTON, self.onUpdate)
        savebutton = wx.Button(self, id=wx.ID_SAVE)
        savebutton.Bind(wx.EVT_BUTTON, self.onSave)
        loadbutton = wx.Button(self, id=wx.ID_OPEN)
        loadbutton.Bind(wx.EVT_BUTTON, self.onLoad)
        self.stopbutton = wx.Button(self, id=wx.ID_STOP)
        self.stopbutton.Bind(wx.EVT_BUTTON, self.onStopCommand)
        self.stopbutton.Disable()
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        button_sizer.Add(self.updatebutton, 0, wx.EXPAND)
        button_sizer.Add(savebutton, 0, wx.EXPAND)
        button_sizer.Add(loadbutton, 0, wx.EXPAND)
        button_sizer.Add(self.stopbutton, 0, wx.EXPAND)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.tree, 1, wx.EXPAND)
        
        panel.SetSizer(sizer)
        
        vsizer = wx.BoxSizer(wx.VERTICAL)
        vsizer.Add(panel, 1, wx.EXPAND)
        vsizer.Add(button_sizer, 0, wx.EXPAND)
        self.SetSizer(vsizer)

        self.Layout()
        
        self.tree.Bind(wx.EVT_TREE_ITEM_EXPANDING, self.onItemExpand, id=1)
        self.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self.onRightClick, self.tree)
        self.Bind(wx.EVT_TREE_SEL_CHANGED, self.onClickItem, self.tree)
        
        self.Bind(EVT_COMMAND_UPDATE, self.onCommandUpdate)
                    
        self.Bind(wx.EVT_IDLE, self.OnIdle)                            
        
    def OnIdle(self, event):
        self.tree.executeNext()
        
    def onItemExpand(self, e):

        item = e.GetItem()
        data = self.tree.GetPyData(item)
        if not data.isExpanded():
            data.expand()

    def onClickItem(self, e):
        item = e.GetItem()
        data = self.tree.GetPyData(item)
        data.handleClick()
        self.config_key = data.ConfigKey()
                
    def onRightClick(self, e):
        item = e.GetItem()
        data = self.tree.GetPyData(item)
        self.PopupMenu(data.GetPopupMenu(), e.GetPoint())

    def onUpdate(self, e):
        seq_config_dict[self.config_key] = self.hdrconfig_panel.hdr_config

    def onCommandUpdate(self, e):
        
        v = e.GetValue()
        thread = e.GetThreadID()
        thread.join() #Ettl lehet, hogy belassul a GUI.
        task_id = e.GetTaskID()
        if e.result == 'Failed':
            self.tree.processingFailed(task_id)
        else:
            self.tree.processingCompleted(task_id)
            if e.callback:
                e.callback(v)
        
        if self.tree.iterator:
            self.stopbutton.Enable()
            self.tree.executeNext()
        else:
            self.stopbutton.Disable()

    def onStopCommand(self, e):
        self.tree.StopCommand()
        self.stopbutton.Disable()
        pid = os.getpid()
        kill_child_processes(pid)
        

    def ShowCustomDialog(self, fd_style):
        dlg = wx.FileDialog(self, "Choose a file", style=fd_style)
        if wx.ID_OK == dlg.ShowModal():
            return dlg.GetPath()
        dlg.Destroy()
        return None

    def onSave(self, e):
        fn = self.ShowCustomDialog(wx.FD_SAVE)
        if fn:
            fout=open(fn, 'w')
            fout.write(pickle.dumps(seq_config_dict))
            fout.close()
    
    def onLoad(self, e):
        fn = self.ShowCustomDialog(wx.FD_OPEN)
        if fn:
            global seq_config_dict
            f=open(fn, "r")
            seq_config_dict=pickle.loads(f.read())
            f.close()
            self._updateHDRConfigPanel()

    
def treeIterator(tree, item):
    yield item
    child, cookie = tree.GetFirstChild(item)
    while child.IsOk():
        for c in treeIterator(tree, child):
            yield c
        child, cookie = tree.GetNextChild(item, cookie)


class TestExpandersApp(wx.App):
    def OnInit(self):


        self.frame = TreeCtrlFrame(None, -1, 'Test expanders', '/')


        self.frame.Show(True)
        self.SetTopWindow(self.frame)
        return True
    
    def OnExit(self):
        kill_child_processes(os.getpid())


seq_config_dict = TreeDict()

def kill_child_processes(parent_pid, sig=signal.SIGTERM):
        ps_command = subprocess.Popen("ps -o pid --ppid %d --noheaders" % parent_pid, shell=True, stdout=subprocess.PIPE)
        ps_output = ps_command.stdout.read()
        ps_pid = ps_command.pid
        retcode = ps_command.wait()
        assert retcode == 0, "ps command returned %d" % retcode
        for pid_str in ps_output.split("\n")[:-1]:
            try:
                os.kill(int(pid_str), sig)
            except OSError:
                print "Kill error", pid_str, ps_pid


if __name__ == "__main__":
    app = TestExpandersApp()
    app.MainLoop()
    print "Finished. # running threads=%d" % TH.active_count()
