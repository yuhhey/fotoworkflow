#-*- coding: utf-8 -*-9

import wx
import os
import errno
import CompositeImage
import copy
import threading as TH


class HDRConfigPanel(wx.Panel):
    
    def __init__(self, *args, **kw):
        self.hdr_config = copy.deepcopy(kw['hdr_config'])
        del kw['hdr_config']
        self.path = kw['path']
        del kw['path']
        #self.hdr_config_dict = kw['hdr_config_dict']
        #del kw['hdr_config_dict']
        
        super(HDRConfigPanel, self).__init__(*args, **kw)
        self.InitUI()

    def inputFieldData(self):
        return (("targetDir", "Target directory:", self.onTargetDir, self.hdr_config.GetTargetDir()),
                ("rawExt", "Raw extension:", self.onRawExtension, self.hdr_config.GetRawExt()),
                ("imageExt", "Output image ext:", self.onImageExt, self.hdr_config.GetImageExt()),
                ("prefix", "Output prefix:", self.onPrefix, self.hdr_config.GetPrefix()),
                ("maxdiff", "Maxdiff:", self.onMaxdiff, str(self.hdr_config.GetCheckers()[0].maxdiff)))

    def setConfig(self, hdr_config, path):
        self.hdr_config = copy.deepcopy(hdr_config)
        self.path = path
        for w, l, h, value in self.inputFieldData():
            getattr(self, w).SetValue(value)

    def createInputField(self, parent, label, handler, defValue= u''):
        cimke = wx.StaticText(parent, -1, label)
        input_field = wx.TextCtrl(parent, -1, defValue, style=wx.TE_LEFT | wx.TE_PROCESS_ENTER)
        
        input_field.Bind(wx.EVT_TEXT_ENTER, handler)
        
        hs = wx.BoxSizer(wx.HORIZONTAL)
        
        hs.Add(cimke, 1, wx.ALIGN_LEFT)
        hs.Add(input_field, 2, wx.ALIGN_CENTER)
        return (input_field, hs)

    def InitUI(self):
        
        sb = wx.StaticBox(self, label='HDR config')
        sbs = wx.StaticBoxSizer(sb, orient=wx.VERTICAL)
        
        for widget, cimke, handler, default_value in self.inputFieldData():
            input_field, hs = self.createInputField(self, cimke, handler, defValue = default_value)
            sbs.Add(hs, 0, wx.EXPAND)
            setattr(self, widget, input_field)
            
        self.SetSizer(sbs)
                
    def updateHDRConfig(self):
        pass

    def onTargetDir(self, evt):
        value = self.targetDir.GetValue()
        self.hdr_config.SetTargetDir(value)
                
    def onRawExtension(self, evt):
        value = self.rawExt.GetValue()
        self.hdr_config.SetRawExt(value)
    
    def onImageExt(self,evt):
        value = self.imageExt.GetValue()
        self.hdr_config.SetImageExt(value)
    
    def onPrefix(self,evt):
        value = self.prefix.GetValue()
        self.hdr_config.SetPrefix(value)
        
    def onMaxdiff(self, evt):
        value = int(self.maxdiff.GetValue())
        self.hdr_config.GetCheckers()[0].maxdiff = value
        print 'onMaxdiff'


class HDRConfigDialog(wx.Dialog):
    def __init__(self, *args, **kw):
        self.hdr_config = kw['hdr_config']
        del kw['hdr_config']
        super(HDRConfigDialog, self).__init__(*args, **kw)
        
        hdr_config_work = copy.deepcopy(self.hdr_config)
        self.panel = HDRConfigPanel(parent = self, hdr_config = hdr_config_work)
        self.InitUI(self.panel)

    def InitUI(self, panel):
        
        hbox2 = wx.BoxSizer(wx.HORIZONTAL)
        okButton = wx.Button(self, label='Ok')
        cancelButton = wx.Button(self, label='Cancel')
        hbox2.Add(okButton)
        hbox2.Add(cancelButton, flag=wx.LEFT, border=5)

        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(panel, proportion=1, 
                 flag=wx.ALL|wx.EXPAND, border=5)
        vbox.Add(hbox2, 
                 flag=wx.ALIGN_CENTER|wx.TOP|wx.BOTTOM, border=10)

        self.SetSizer(vbox)
        
        okButton.Bind(wx.EVT_BUTTON, self.onOk)
        cancelButton.Bind(wx.EVT_BUTTON, self.onCancel)
            
    def onOk(self,evt):
        self.hdr_config.SetTargetDir(self.panel.targetDir.GetValue())
        self.hdr_config.SetRawExt(self.panel.rawExt.GetValue())
        self.hdr_config.SetImageExt(self.panel.imageExt.GetValue())
        self.hdr_config.SetPrefix(self.panel.prefix.GetValue())
        
        self.onCancel(evt)
                
    def onCancel(self, evt):
        self.Destroy()


class Command:
    def __init__(self, notify_window):
        self._notify_window = notify_window
        self._want_abort = 0
    
    def Finished(self,data):
        pass
        #wx.PostEvent(self._notify_window, data)
        
    def abort(self):    
        self._want_abort = 1
        
    def abortWanted(self):
        return self._want_abort != 0
    
    def __call__(self):
        print "What command is that can not be called!"
        raise NotImplementedError


class recursiveCommand(Command):
    def __init__(self, tree, itemID, gen):
        Command.__init__(self, tree)
        self.tree = tree
        self.itemID = itemID
        self.gen = gen
        
    def __call__(self):
        for i in treeIterator(self.tree, self.itemID):
            if self.abortWanted():
                wx.PostEvent(self._notify_window, None)
            data = self.tree.GetPyData(i)
            data.executeGen(self.gen)

 
class WorkerThread(TH.Thread):
    """Worker Thread Class."""
    def __init__(self, cmd):
        """Init Worker Thread Class."""
        TH.Thread.__init__(self)
        self._cmd = cmd
        # This starts the thread running on creation, but you could
        # also make the GUI thread responsible for calling this
        self.start()

    def run(self):
        """Run Worker Thread."""
        self._cmd()
        
    def abort(self):
        self._cmd.abort()


class ExpanderPopup(wx.Menu):
    def __init__(self):
        wx.Menu.__init__(self)

    def addItem(self, label, callback):
        item = wx.MenuItem(self, wx.NewId(), label)
        self.AppendItem(item)
        self.Bind(wx.EVT_MENU, callback, item)
        return item
    
    def buildMenu(self, items):
        for l, c in items: 
            self.addItem(l, c)    

    
class Expander(object):
    # TODO: menu item kezelés az ImageSequenceExpanderPopup-ból.
    def __init__(self, tree, itemID):
        
        self.tree = tree
        self.itemID = itemID
        self.tree.SetPyData(itemID, self)
        
    def isExpanded(self):
        raise NotImplementedError
                            
    def expand(self, *arsg, **kwargs):
        pass
        #raise NotImplementedError
    
    def getPopupMenu(self, *args, **kwargs):
        raise NotImplementedError
    
    # TODO: megfontolandó, hogy ez különálló függvény legyen - e egy plusz tree paraméterrel

    def handleClick(self, control):
        raise NotImplementedError
    
    def itemHasChildOfType(self, item, t):
        (child, cookie) = self.tree.GetFirstChild(item)
        while child.IsOk():
            pydata = self.tree.GetPyData(child)
            if isinstance(pydata, t):
                return pydata
            (child, cookie) = self.tree.GetNextChild(self.itemID, cookie)
        
        return None
    
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
        
    def findTypeAbove(self, t):
        """Checks if a child in higher level in the tree of type 't' exists"""
        p = self.tree.GetItemParent(self.itemID)
        return self.findType(p, t)
        
    def executeGen(self, dummyarg):
        pass

           
class DirectoryExpanderPopup(ExpanderPopup):
    def __init__(self, parent_window, d_expander):
        ExpanderPopup.__init__(self)
        self.dir_expander = d_expander
        
        menu_items = [("HDR config", self.onHDRConf),
                      ("Panorama config", self.onPanoramaConf),
                      ("Symlinks", self.onSymlinks),
                      ("Generate HDR", self.onHDRGen)]
        
        self.buildMenu(menu_items)
    
        self.parent_window = parent_window
        
    def onHDRConf(self, evt):
        print evt, type(evt)
        raise NotImplementedError  
        
    def onPanoramaConf(self, evt):
        raise NotImplementedError

    def onSymlinks(self, evt):
        self.dir_expander.genSymlink()
        
    def onHDRGen(self,evt):
        self.dir_expander.genHDR()


class DirectoryExpander(Expander):
    def __init__(self, tree, path, itemID = None):
        #FIXME: turn it to assert
        if not os.path.isdir(path):
            raise OSError(errno.ENOENT, os.strerror(errno.ENOENT))
        self.path = path
        if itemID == None:
            itemID = tree.AddRoot(path)
        
        tree.SetItemHasChildren(itemID)
        self.expanded = False
        Expander.__init__(self,tree, itemID)
        
    def isExpanded(self):
        return self.expanded
 
 
    def onDirListReady(self, list):
        self.tree.clearState(self.itemID)
        
        for fn in sorted(list):
            fullpath = os.path.join(self.path, fn)
            if os.path.isdir(fullpath):
                child = self.tree.AppendItem(self.itemID, fn)
                DirectoryExpander(self.tree, fullpath, child)
                
       
        # Here we shall parse for image sequences.
        hdr_config = hdr_config_dict[self.path]
                
        # Ezt kell Thread commandba foglalni.
        try: 
            hdrs, single_images = CompositeImage.CollectHDRStrategy().parseDir(self.path, hdr_config)
            
        except IOError:  # handling the case when there are no raw files
            print "No RAW input to parse in %s" % self.path    
              
    def onHDRParsed(self, (hdrs, single_images)):
        self.tree.clearState(self.itemID)
        
        n_hdrs = len(hdrs)
        if n_hdrs == 0:
            return
        
        item_text = self.tree.GetItemText(self.itemID)
        item_text = item_text + "(%d hdrs)" % n_hdrs
        self.tree.SetItemText(self.itemID, item_text)
            
        prefix = hdr_config.GetPrefix()
        hdr_path = hdr_config.GetTargetDir()
        for fn, seq in enumerate(reversed(hdrs)):
            actual_prefix = prefix + "_%d" % fn  
            target_path = os.path.join(hdr_path, actual_prefix)
            child = self.tree.AppendItem(self.itemID, target_path)
            ImageSequenceExpander(self.tree, target_path, child, seq)
            hdr_config_per_image = copy.deepcopy(hdr_config)
            hdr_config_per_image.SetPrefix(actual_prefix)
            hdr_config_dict[target_path] = hdr_config_per_image

    def onProgressTimer(self):
        # Ha több mint egy thread van, akkor a timer újra indítjuk
        pass
        
    def expand(self):

        if self.isExpanded():
            return
        
        self.tree.processingStarted(self.itemID)
        # Here we start a timer for the progress indicator
        
        #Ezt kell threadbe foglalni
        os.listdir(self.path)
        
        
               
        self.expanded = True
 
    def getPopupMenu(self, parent_window):
        return DirectoryExpanderPopup(parent_window, self)
    
    def handleClick(self, control):
        hdr_config = hdr_config_dict[self.path]
        control.hdrconfig_panel.setConfig(hdr_config, self.path)

    def executeGen(self,gen):
        print self.path, "executeGen"
        self.expand()

    def cmdExec(self,gen):
        # EZ nem ilyen egyszerű, mivel az expand gyorsan visszatér, ezért rengeteg threaded gyártana le.
        wt = recursiveCommand(self.tree, self.itemID, gen)
            
    def genSymlink(self):
        self.cmdExec(CompositeImage.SymlinkGenerator())
 
            
    def genHDR(self):
        self.cmdExec(CompositeImage.HDRGenerator())


class ImageExpander(Expander):
    def __init__(self, tree, itemID, image):
        Expander.__init__(self,tree, itemID)
        self.image = image


class ImageSequenceExpanderPopup(ExpanderPopup):
    
    #TODO: Megnézni, hogy nem elég-e az expander.executeGen függvényt átadni paraméterként.
    def __init__(self, expander):
        wx.Menu.__init__(self)
        self.expander = expander
        menu_items = [("Generate", self.onGenerate),
                      ("Symlinks", self.onCreateSymlink)]
        self.buildMenu(menu_items)
   
    def onGenerate(self, evt):
        self.expander.executeGen(CompositeImage.HDRGenerator())
        
    def onCreateSymlink(self,evt):
        self.expander.executeGen(CompositeImage.SymlinkGenerator())


class ImageSequenceExpander(Expander):
    def __init__(self, tree, target_path, itemID, img_seq):
        Expander.__init__(self, tree, itemID)
        self.target_path=target_path
        self.seq = img_seq
        if len(self.seq) > 0:
            tree.SetItemHasChildren(itemID)
            
        #self.path = img_seq.getFilelist()[0]
        self.expanded = False
     
    def isExpanded(self):
        return self.expanded
    
    def expand(self):
        # TODO: Minden egyes alkalommal újra kell számolni
        if self.isExpanded():
            return
        for img in sorted(self.seq):
            child = self.tree.AppendItem(self.itemID, os.path.basename(img))
            ImageExpander(self.tree, child, self.seq[img])
        self.expanded = True

    
    def handleClick(self, control):
        hdr_config = hdr_config_dict[self.target_path]
        control.hdrconfig_panel.setConfig(hdr_config, self.target_path)
        
    def getPopupMenu(self, parent_window):
        return ImageSequenceExpanderPopup(self)
    
    def executeGen(self, gen):
        #self.tree.processingStarted(self.itemID)
        seq = self.seq
        path = self.target_path
        hdr_config = hdr_config_dict[path]
        gen(seq, hdr_config)
        #self.tree.processingCompleted(self.itemID)

    
class TreeDict:
    """ A dictionary which assumes keys are directory paths. It looks up elements with key up in the path"""
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
        del self.d[key]
                
    def __len__(self):
        return len(self.d)


    def __contains__(self, key):
        return key in self.d.keys()

    def keys(self):
        return self.d.keys()
     

class TreeCtrlWithImages(wx.TreeCtrl):
    def __init__(self, *args, **kwrds):
        
        wx.TreeCtrl.__init__(self, *args, **kwrds)
        # bitmaps for progress indication.
        self.il = wx.ImageList(16,16)
        self.AssignImageList(self.il)
        self.imgs_wip = [self.il.Add(wx.ArtProvider.GetBitmap(wx.ART_QUESTION, wx.ART_OTHER, (16,16)))]
        self.img_ready = self.il.Add(wx.ArtProvider.GetBitmap(wx.ART_TICK_MARK, wx.ART_OTHER, (16,16)))
        self.img_aborted = self.il.Add(wx.ArtProvider.GetBitmap(wx.ART_CROSS_MARK, wx.ART_OTHER, (16,16)))
        
        # Init for progress animation
        self.processedItem = None
        self.processImageIndex = 0
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.updateProgress, self.timer)
        
    def processingStarted(self, item):
        self.processedItem = item
        self.SetItemImage(item, self.imgs_wip[0],wx.TreeItemIcon_Normal)
        
        self.timer.Start(100) #in milliseconds
        
    def updateProgress(self):
        self.processImageIndex = (self.processImageIndex + 1) % len(self.imgs_wip)
        self.SetItemImage(item, self.imgs_wip[self.processImageIndex], wx.TreeItemIcon_Normal)
            
    def processingCompleted(self, item):
        self.SetItemImage(item, self.img_ready,wx.TreeItemIcon_Normal)
        self.timer.Stop()
        
    def processingFailed(self, item):
        self.SetItemImage(item, self.img_aborted,wx.TreeItemIcon_Normal)
        self.timer.Stop()
        
    def clearState(self, item):
        self.SetItemImage(item, -1,wx.TreeItemIcon_Normal)
  
        
class TreeCtrlFrame(wx.Frame):
    
    def __init__(self, parent, id, title, rootdir):
        
        
        
        wx.Frame.__init__(self, parent, id, title, wx.DefaultPosition, wx.Size(450, 350))
        panel = wx.Panel(self, -1)
        self.tree = TreeCtrlWithImages(panel, 1, wx.DefaultPosition, (-1,-1), wx.TR_HAS_BUTTONS)
        
        
        #self.path = rootdir
        expander = DirectoryExpander(self.tree, rootdir)
        
        self.updatebutton = wx.Button(panel, label='Update')
        self.updatebutton.Bind(wx.EVT_BUTTON, self.onUpdate)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.tree, 1, wx.EXPAND)
        sizer.Add(self.updatebutton, 0, wx.EXPAND)
        panel.SetSizer(sizer)
        
        hdr_config_dict[rootdir] = CompositeImage.HDRConfig('/tmp')
        self.hdrconfig_panel = HDRConfigPanel(hdr_config=hdr_config_dict[rootdir],
                                              path=rootdir,
                                              parent=self)
        
        hsizer = wx.BoxSizer(wx.HORIZONTAL)
        hsizer.Add(panel, 1, wx.EXPAND)
        hsizer.Add(self.hdrconfig_panel, 1, wx.EXPAND)
        self.SetSizer(hsizer)
        #sizer.Fit(self)
        self.Layout()
        
        self.tree.Bind(wx.EVT_TREE_ITEM_EXPANDING, self.onItemExpand, id=1)
        self.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self.onRightClick, self.tree)
        self.Bind(wx.EVT_TREE_SEL_CHANGED, self.onClickItem, self.tree)
                    
    def onItemExpand(self, e):

        item = e.GetItem()
        data = self.tree.GetPyData(item)
        if not data.isExpanded():
            data.expand()
        
    def onClickItem(self, e):
        item = e.GetItem()
        data = self.tree.GetPyData(item)
        data.handleClick(self)
        self.path = data.path
        
        
        
    def onRightClick(self, e):
        item = e.GetItem()
        data = self.tree.GetPyData(item)
        self.PopupMenu(data.getPopupMenu(self), e.GetPoint())

    def onUpdate(self, e):
        hdr_config_dict[self.path] = self.hdrconfig_panel.hdr_config
        for k in hdr_config_dict.keys():
            print k, hdr_config_dict[k]


def treeIterator(tree, item):
    yield item
    child, cookie = tree.GetFirstChild(item)
    while child.IsOk():
        for c in treeIterator(tree, child):
            yield c
        child, cookie = tree.GetNextChild(item, cookie)


class TestExpandersApp(wx.App):
    def OnInit(self):
        frame = TreeCtrlFrame(None, -1, 'Test expanders', '/home')#media/misc/MM/Filmek/Nepal/CR2')#storage/Kepek/kepek_eredeti/CR2/2012_04_02') #
        frame.Show(True)
        self.SetTopWindow(frame)
        return True

hdr_config_dict = TreeDict()


if __name__ == "__main__":
    app = TestExpandersApp()
    app.MainLoop()

