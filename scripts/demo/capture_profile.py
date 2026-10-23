"""Disable recovery saves before GUI startup and verify the actual Qt timers.

Changing AutoSaveEnabled in a running GUI does not stop AutoSaver's existing
per-document timers. Startup must read the disabled preference/zero timeout.
"""
import argparse,json,shutil,time
from pathlib import Path
import xml.etree.ElementTree as ET

def configure(profile):
 profile=Path(profile);path=profile/'user.cfg'
 if path.exists():
  backup=profile.parent/'trash'/('capture-config-'+str(time.time_ns()))
  backup.mkdir(parents=True);shutil.copy2(path,backup/'user.cfg')
  root=ET.parse(path).getroot()
 else:root=ET.Element('FCParameters')
 def group(parent,name):
  child=parent.find("FCParamGroup[@Name='%s']"%name)
  return child if child is not None else ET.SubElement(parent,'FCParamGroup',Name=name)
 prefs=group(group(group(root,'Root'),'BaseApp'),'Preferences')
 for section,tag,name,value in [('Document','FCBool','AutoSaveEnabled','0'),('Document','FCInt','AutoSaveTimeout','0'),('NotificationArea','FCBool','NonIntrusiveNotificationsEnabled','0')]:
  parent=group(prefs,section);child=parent.find("%s[@Name='%s']"%(tag,name))
  if child is None:child=ET.SubElement(parent,tag,Name=name)
  child.set('Value',value)
 path.write_bytes(ET.tostring(root,encoding='UTF-8',xml_declaration=True))

def capture_status():
 import FreeCAD as App
 from PySide import QtCore,QtWidgets
 app=QtWidgets.QApplication.instance();timers=[];objects=[]
 for obj in app.findChildren(QtCore.QObject):
  if obj.metaObject().className().endswith('AutoSaver'):
   objects.append(obj.metaObject().className())
   dispatcher=QtCore.QAbstractEventDispatcher.instance(obj.thread())
   timers.extend(int(t.interval) for t in dispatcher.registeredTimers(obj))
 return {'auto_save':App.ParamGet('User parameter:BaseApp/Preferences/Document').GetBool('AutoSaveEnabled'),
         'popup_notifications':App.ParamGet('User parameter:BaseApp/Preferences/NotificationArea').GetBool('NonIntrusiveNotificationsEnabled'),
         'auto_save_timer_intervals_ms':timers,'auto_saver_objects':len(objects)}

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('profile',type=Path)
 configure(parser.parse_args().profile)
