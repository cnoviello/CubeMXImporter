#!/usr/bin/python

# Copyright (c) 2015 Carmine Noviello
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

version = 0.1

import os
import argparse
import copy
import logging
import shutil
import re
from lxml import etree

class CubeMXImporter(object):
    """docstring for CubeMXImporter"""
    def __init__(self):
        super(CubeMXImporter, self).__init__()
        
        self.eclipseprojectpath = ""
        self.dryrun = 0
        self.logger = logging.getLogger(__name__)
        self.HAL_TYPE = None

    def setCubeMXProjectPath(self, path):
        """Set the path of CubeMX generated project folder"""

        if os.path.exists(os.path.join(path, ".mxproject")): 
            if os.path.exists(os.path.join(path, "SW4STM32")): 
                self.cubemxprojectpath = path
                self.detectHALInfo()
            else:
                raise InvalidSW4STM32Project("The generated CubeMX project is not for SW4STM32 tool-chain. Please, regenerate the project again.")
        else:
            raise InvalidCubeMXFolder("The folder '%s' doesn't seem a CubeMX project" % path)
            
    def getCubeMXProjectPath(self):
        """Retrieve the path of CubeMX generated project folder"""        
        return self.cubemxprojectpath
        
    cubeMXProjectPath = property(getCubeMXProjectPath, setCubeMXProjectPath)


    def setEclipseProjectPath(self, path):
        """Set the path of Eclipse generated project folder"""

        if os.path.exists(os.path.join(path, ".cproject")):
            self.eclipseprojectpath = path
        else:
            raise InvalidEclipseFolder("The folder '%s' doesn't seem an Eclipse project" % path)
            
    def getEclipseProjectPath(self):
        """Retrieve the path of Eclipse generated project folder"""        
        return self.eclipseprojectpath
        
    eclipseProjectPath = property(getEclipseProjectPath, setEclipseProjectPath)
        
    def __addOptionValuesToProject(self, values, section, quote=True):
        if self.dryrun: return
        """Add a list of option values into a given section in the Eclipse project file"""
        options = self.projectRoot.xpath("//option[@superClass='%s']" % section) #Uses XPATH to retrieve the 'section'
        optionsValues = [o.attrib["value"] for o in options[0]] #List all available values to avoid reinsert again the same value
        for opt in options:
            for v in values:
                pattern = '"%s"' if quote else '%s' #The way how include paths and macros are stored differs. Include paths are quoted with ""
                if pattern % v not in optionsValues: #Avoid to place the same include again
                    listOptionValue = copy.deepcopy(opt[0])
                    if quote:
                        listOptionValue.attrib["value"] = "&quot;%s&quot;" % v #Quote the path
                    else:
                        listOptionValue.attrib["value"] = "%s" % v
                    opt.append(listOptionValue)

    def addAssemblerIncludes(self, includes):
        """Add a list of include paths to the Assembler section in project settings"""
        self.__addOptionValuesToProject(includes, "ilg.gnuarmeclipse.managedbuild.cross.option.assembler.include.paths")

    def addCIncludes(self, includes):
        """Add a list of include paths to the C section in project settings"""
        self.__addOptionValuesToProject(includes, "ilg.gnuarmeclipse.managedbuild.cross.option.c.compiler.include.paths")

    def addCPPIncludes(self, includes):
        """Add a list of include paths to the CPP section in project settings"""
        self.__addOptionValuesToProject(includes, "ilg.gnuarmeclipse.managedbuild.cross.option.cpp.compiler.include.paths")


    def addAssemblerMacros(self, macros):
        """Add a list of macros to the CPP section in project settings"""
        self.__addOptionValuesToProject(macros, "ilg.gnuarmeclipse.managedbuild.cross.option.assembler.defs", False)

    def addCMacros(self, macros):
        """Add a list of macros to the CPP section in project settings"""
        self.__addOptionValuesToProject(macros, "ilg.gnuarmeclipse.managedbuild.cross.option.c.compiler.defs", False)
                        
    def addCPPMacros(self, macros):
        """Add a list of macros to the CPP section in project settings"""
        self.__addOptionValuesToProject(macros, "ilg.gnuarmeclipse.managedbuild.cross.option.cpp.compiler.defs", False)

    def copyTreeContent(self, src, dst):
        """Copy all files contsined in 'src' folder to 'dst' folder"""
        files = os.listdir(src)
        for f in files:
            fileToCopy = os.path.join(src, f)
            if os.path.isfile(fileToCopy):
                logging.debug("Copying %s to %s" % (fileToCopy, dst))
                if not self.dryrun:
                    shutil.copyfile(fileToCopy, os.path.join(dst, f))
            elif os.path.isdir(fileToCopy):
                logging.debug("Copying folder %s to %s" % (fileToCopy, dst))
                if not self.dryrun:
                    shutil.copytree(fileToCopy, os.path.join(dst, f))

    def deleteOriginalEclipseProjectFiles(self):
        """Deletes useless files generated by the GNU ARM Eclipse plugin"""
        
        dirs = ["src", "include", "system/src/cmsis", "system/src/stm32%sxx" % self.HAL_TYPE.lower(), "system/include/stm32%sxx" % self.HAL_TYPE.lower()]

        [self.deleteTreeContent(os.path.join(self.eclipseprojectpath, d)) for d in dirs]

        files = ["system/include/cmsis/stm32%sxx.h" % self.HAL_TYPE.lower(), "system/include/cmsis/system_stm32%sxx.h" % self.HAL_TYPE.lower()]
        
        try:
            if not self.dryrun:
                [os.unlink(os.path.join(self.eclipseprojectpath, f)) for f in files]
        except OSError:
            pass

        self.logger.info("Deleted uneeded files generated by GNU Eclipse plugin")

    def deleteTreeContent(self, tree):
        """Delete all files contained in a given folder"""
        for f in os.listdir(tree):
            f = os.path.join(tree, f)
            logging.debug("Deleting %s" % f)
            if not self.dryrun:
                if os.path.isfile(f):
                    os.unlink(f)
                elif os.path.isdir(f):
                    shutil.rmtree(f)

    def detectHALInfo(self):
        """Scans the SW4STM32 project file looking for relevant informations about MCU and HAL types"""

        root = None

        for root, dirs, files in os.walk(os.path.join(self.cubemxprojectpath, "SW4STM32")):
            if ".cproject" in files:
                root = etree.fromstring(open(os.path.join(root, ".cproject")).read())

        if root is None:
            raise InvalidSW4STM32Project("The generated CubeMX project is not for SW4STM32 tool-chain. Please, regenerate the project again.")

        options = root.xpath("//option[@superClass='gnu.c.compiler.option.preprocessor.def.symbols']")[0]

        for opt in options:
            if "STM32" in opt.attrib["value"]:
                self.HAL_MCU_TYPE = opt.attrib["value"]
                self.HAL_TYPE = re.split("([F,L]{1}[0-9]{1})", self.HAL_MCU_TYPE)[1]
                self.logger.info("Detected MCU type: %s" % self.HAL_MCU_TYPE)
                self.logger.info("Detected HAL type: %s" % self.HAL_TYPE)

    def importApplication(self):
        """Import generated application code inside the Eclipse project"""
        srcIncludeDir = os.path.join(self.cubemxprojectpath, "Inc")
        srcSourceDir = os.path.join(self.cubemxprojectpath, "Src")
        dstIncludeDir = os.path.join(self.eclipseprojectpath, "include")
        dstSourceDir = os.path.join(self.eclipseprojectpath, "src")

        locations = ((srcIncludeDir, dstIncludeDir), (srcSourceDir, dstSourceDir))

        for loc in locations:
            self.copyTreeContent(loc[0], loc[1])

        self.logger.info("Successfully imported application files")

    def importCMSIS(self):
        """Import CMSIS package and CMSIS-DEVICE adapter by ST inside the Eclipse project"""
        srcIncludeDir = os.path.join(self.cubemxprojectpath, "Drivers/CMSIS/Device/ST/STM32%sxx/Include" % self.HAL_TYPE)
        dstIncludeDir = os.path.join(self.eclipseprojectpath, "system/include/cmsis/device")
        srcCMSISIncludeDir = os.path.join(self.cubemxprojectpath, "Drivers/CMSIS/Include")
        dstCMSISIncludeDir = os.path.join(self.eclipseprojectpath, "system/include/cmsis")
        dstSourceDir = os.path.join(self.eclipseprojectpath, "system/src/cmsis")

        try:
            if not self.dryrun:
                os.mkdir(dstIncludeDir)
        except OSError:
            pass

        #Add includes to the project settings
        self.addCIncludes(("../system/include/cmsis/device",))
        self.addCPPIncludes(("../system/include/cmsis/device",))
        self.addAssemblerIncludes(("../system/include/cmsis/device",))

        # locations = ((srcIncludeDir, dstIncludeDir), (srcSourceDir, dstSourceDir))
        locations = ((srcIncludeDir, dstIncludeDir), (srcCMSISIncludeDir, dstCMSISIncludeDir))

        for loc in locations:
            self.copyTreeContent(loc[0], loc[1])

        systemFile = os.path.join(self.cubemxprojectpath, "Drivers/CMSIS/Device/ST/STM32%sxx/Source/Templates/system_stm32%sxx.c" % (self.HAL_TYPE, self.HAL_TYPE.lower()))
        startupFile = os.path.join(self.cubemxprojectpath, "Drivers/CMSIS/Device/ST/STM32%sxx/Source/Templates/gcc/startup_%s.s" % (self.HAL_TYPE, self.HAL_MCU_TYPE.lower()))
            
        locations = ((systemFile, dstSourceDir), (startupFile, dstSourceDir))

        if not self.dryrun:
            for loc in locations:
                shutil.copy(loc[0], loc[1])

            os.rename(os.path.join(self.eclipseprojectpath, "system/src/cmsis/startup_%s.s" % self.HAL_MCU_TYPE.lower()), os.path.join(self.eclipseprojectpath, "system/src/cmsis/startup_%s.S" % self.HAL_MCU_TYPE.lower()))
    
        self.logger.info("Successfully imported CMSIS files")

    def importHAL(self):
        """Import the ST HAL inside the Eclipse project"""
        srcIncludeDir = os.path.join(self.cubemxprojectpath, "Drivers/STM32%sxx_HAL_Driver/Inc" % self.HAL_TYPE)
        srcSourceDir = os.path.join(self.cubemxprojectpath, "Drivers/STM32%sxx_HAL_Driver/Src" % self.HAL_TYPE)
        dstIncludeDir = os.path.join(self.eclipseprojectpath, "system/include/stm32%sxx" % self.HAL_TYPE.lower())
        dstSourceDir = os.path.join(self.eclipseprojectpath, "system/src/stm32%sxx" % self.HAL_TYPE.lower())

        locations = ((srcIncludeDir, dstIncludeDir), (srcSourceDir, dstSourceDir))

        for loc in locations:
            self.copyTreeContent(loc[0], loc[1])

        self.addAssemblerMacros((self.HAL_MCU_TYPE,))
        self.addCMacros((self.HAL_MCU_TYPE,))
        self.addCPPMacros((self.HAL_MCU_TYPE,))

        if not self.dryrun:
            os.unlink(os.path.join(self.eclipseprojectpath, "system/src/stm32%sxx/stm32%sxx_hal_msp_template.c" % (self.HAL_TYPE.lower(), self.HAL_TYPE.lower())))

        self.logger.info("Successfully imported the STCubeHAL")
        
    def parseEclipseProjectFile(self):
        """Parse the Eclipse XML project file"""
        projectFile = os.path.join(self.eclipseprojectpath, ".cproject")
        self.projectRoot = etree.fromstring(open(projectFile).read())
        
    def printEclipseProjectFile(self):
        """Do a pretty print of Eclipse project DOM"""
        xmlout = etree.tostring(self.projectRoot, pretty_print=True)
        #lxml correctly escapes the "&" to "&amp;", as specified by the XML standard.
        #However, Eclipse expects that the " charachter is espressed as &quot; So,
        #here we replace the "&amp;" with "&" in the final XML file
        xmlout = xmlout.replace("&amp;", "&")
        print xmlout

    def saveEclipseProjectFile(self):
        """Save the XML DOM of Eclipse project inside the .cproject file"""

        xmlout = '<?xml version="1.0" encoding="UTF-8" standalone="no"?><?fileVersion 4.0.0?>' + etree.tostring(self.projectRoot)
        #lxml correctly escapes the "&" to "&amp;", as specified by the XML standard.
        #However, Eclipse expects that the " charachter is espressed as &quot; So,
        #here we replace the "&amp;" with "&" in the final XML file
        xmlout = xmlout.replace("&amp;", "&")
        projectFile = os.path.join(self.eclipseprojectpath, ".cproject")
        if not self.dryrun:
            open(projectFile, "w+").write(xmlout)

    def setDryRun(self, dryrun):
        """Enable dryrun mode: it does't execute operations on projects"""
        self.dryrun = dryrun
        if(dryrun > 0):
            self.logger.debug("Running in DryRun mode: the Eclipse project will not be modified")

class InvalidCubeMXFolder(Exception):
    pass
            
class InvalidEclipseFolder(Exception):
    pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Import a CubeMX generated project inside an existing Eclipse project generated with the GNU ARM plugin')
    
    parser.add_argument('eclipse_path', metavar='eclipse_project_folder', type=str, 
                       help='an integer for the accumulator')

    parser.add_argument('cubemx_path', metavar='cubemx_project_folder', type=str, 
                       help='an integer for the accumulator')

    parser.add_argument('-v', '--verbose', type=int, action='store',
                       help='Verbose level')

    parser.add_argument('--dryrun', action='store_true', 
                       help="Doesn't perform operations - for debug purpose")

    args = parser.parse_args()

    if args.verbose == 3:
        logging.basicConfig(level=logging.DEBUG)
    if args.verbose == 2:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.ERROR )

    cubeImporter =  CubeMXImporter()
    cubeImporter.setDryRun(args.dryrun)
    cubeImporter.eclipseProjectPath = args.eclipse_path
    cubeImporter.cubeMXProjectPath = args.cubemx_path
    cubeImporter.parseEclipseProjectFile()
    cubeImporter.deleteOriginalEclipseProjectFiles()
    cubeImporter.importApplication()
    cubeImporter.importHAL()
    cubeImporter.importCMSIS()
    cubeImporter.saveEclipseProjectFile()
    # cubeImporter.addCIncludes(["../middlewares/freertos"])
    # cubeImporter.printEclipseProjectFile()