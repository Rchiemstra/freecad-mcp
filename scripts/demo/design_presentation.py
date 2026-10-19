"""Submit through MCP execute_code: Qt presentation cadence only; no CAD mutation."""
from PySide import QtCore, QtWidgets
import FreeCADGui as Gui
class DesignPresentationCadence(QtCore.QObject):
 @QtCore.Slot()
 def start(self):
  window=Gui.getMainWindow()
  self.pulse=QtCore.QTimer(window)
  def adjust():
   activity=window.findChild(QtCore.QTimer,'activityTimer')
   if activity and activity.isActive() and activity.interval()>8: activity.setInterval(8)
  self.pulse.timeout.connect(adjust)
  self.pulse.start(8)
  adjust()
_design_cadence=DesignPresentationCadence()
_design_cadence.moveToThread(QtWidgets.QApplication.instance().thread())
QtCore.QMetaObject.invokeMethod(_design_cadence,'start',QtCore.Qt.QueuedConnection)
print('Queued GUI-only presentation timer cadence: 8 ms. No geometry or mutation barriers changed.')
