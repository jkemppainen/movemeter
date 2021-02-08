'''
A tkinter GUI for Movemeter.
'''

import os
import csv
import json
import datetime
import zipfile
import inspect

import numpy as np
import tifffile
import tkinter as tk
from tkinter import filedialog, simpledialog
import matplotlib.patches
from PIL import Image

from tk_steroids.elements import Listbox, Tabs, TickboxFrame, ButtonsFrame
from tk_steroids.matplotlib import CanvasPlotter

from movemeter import __version__
from movemeter.directories import MOVEDIR
from movemeter import gen_grid
from movemeter import Movemeter


class MovemeterTkGui(tk.Frame):
    '''
    Class documentation TODO.
    
    
    exclude_images : list of integers and/or strings
        Images to skip by file name or by index
    '''

    def __init__(self, tk_parent):
        tk.Frame.__init__(self, tk_parent)
        self.parent = tk_parent

        self.current_folder = None
        self.folders = []
        self.image_fns = []
        self.images = None
        self.exclude_images = []

        self.selection = [0,0,10,10]
        self.mask_image = None
        self.rois = []
        self.roi_patches = []
        self.results = []
        
        self.heatmap_images = []
        
        self.movemeter = None
        self.fs = 100

        # Top menu
        # --------------------------------
        self.menu = tk.Menu(self)
        
        filemenu = tk.Menu(self)
        filemenu.add_command(label='Open directory', command=self.open_directory)
        filemenu.add_command(label='Reprocess old', command=self.recalculate_old)
        self.menu.add_cascade(label='File', menu=filemenu)
        

        self.parent.config(menu=self.menu)

        # Input folders

        self.folview = tk.LabelFrame(self, text='Input folders')
        self.folview.rowconfigure(2, weight=1)
        self.folview.columnconfigure(1, weight=1)
        self.folview.grid(row=0, column=1, sticky='NSWE')

        self.folders_listbox = Listbox(self.folview, ['No folders selected'], self.folder_selected)
        self.folders_listbox.listbox.config(height=10)
        self.folders_listbox.grid(row=2, column=1, columnspan=2, sticky='NSWE')

        self.imview_buttons = ButtonsFrame(self.folview,
                ['Add...', 'Remove', 'FS'],
                [self.open_directory, self.remove_directory, self.set_fs])
        self.imview_buttons.grid(row=0, column=1) 
        self.fs_button = self.imview_buttons.buttons[2]
        self.set_fs(fs=self.fs)

        # Operations view
        # -------------------------
        self.opview = tk.LabelFrame(self, text='Command center')
        self.opview.grid(row=0, column=2, sticky='NSWE')
        
        self.roiview = tk.LabelFrame(self.opview, text='ROI gird creation options')
        self.roiview.columnconfigure(2, weight=1)
        self.roiview.grid(row=2, column=1, columnspan=2, sticky='NSWE')
        
        tk.Label(self.roiview, text='Block size').grid(row=1, column=1)
        self.blocksize_slider = tk.Scale(self.roiview, from_=16, to=128,
                orient=tk.HORIZONTAL)
        self.blocksize_slider.set(32)
        self.blocksize_slider.grid(row=1, column=2, sticky='NSWE')

        tk.Label(self.roiview, text='Relative distance').grid(row=2, column=1)
        self.overlap_slider = tk.Scale(self.roiview, from_=0.1, to=2,
                orient=tk.HORIZONTAL, resolution=0.1)
        self.overlap_slider.set(1)
        self.overlap_slider.grid(row=2, column=2, sticky='NSWE')
        
        self.update_grid_button = tk.Button(self.roiview, text='Update grid',
                command=self.update_grid)
        self.update_grid_button.grid(row=3, column=1)

        self.fill_grid_button = tk.Button(self.roiview, text='Create maxgrid',
                command=self.fill_grid)
        self.fill_grid_button.grid(row=3, column=2)



        self.parview = tk.LabelFrame(self.opview, text='Movemeter parameters')
        self.parview.columnconfigure(2, weight=1)
        self.parview.grid(row=3, column=1, columnspan=2, sticky='NSWE')


        # Movemeter True/False options; Automatically inspect from Movemeter.__init__
        moveinsp = inspect.getfullargspec(Movemeter.__init__)

        moveargs = []
        movedefaults = []
        for i in range(1, len(moveinsp.args)):
            arg = moveinsp.args[i]
            default = moveinsp.defaults[i-1]
            if isinstance(default, bool) and arg not in ['multiprocess']:
                moveargs.append(arg)
                movedefaults.append(default)
        
        self.movemeter_tickboxes = TickboxFrame(self.parview, moveargs,
                defaults=movedefaults)
        self.movemeter_tickboxes.grid(row=0, column=1, columnspan=2)


        tk.Label(self.parview, text='Maximum movement').grid(row=1, column=1)
        self.maxmovement_slider = tk.Scale(self.parview, from_=1, to=100,
                orient=tk.HORIZONTAL)
        self.maxmovement_slider.set(10)
        self.maxmovement_slider.grid(row=1, column=2, sticky='NSWE')

        tk.Label(self.parview, text='Upscale').grid(row=2, column=1)
        self.upscale_slider = tk.Scale(self.parview, from_=0.1, to=10,
                orient=tk.HORIZONTAL, resolution=0.1)
        self.upscale_slider.set(5)
        self.upscale_slider.grid(row=2, column=2, sticky='NSWE')


        tk.Label(self.parview, text='CPU cores').grid(row=3, column=1)
        self.cores_slider = tk.Scale(self.parview, from_=1, to=os.cpu_count(),
                orient=tk.HORIZONTAL)
        self.cores_slider.set(max(1, int(os.cpu_count()/2)))
        self.cores_slider.grid(row=3, column=2, sticky='NSWE')


        

        self.calculate_button = tk.Button(self.opview, text='Measure movement',
                command=self.measure_movement)
        self.calculate_button.grid(row=1, column=1)

        self.stop_button = tk.Button(self.opview, text='Stop',
                command=self.stop)
        self.stop_button.grid(row=1, column=2)


        self.export_button = tk.Button(self.opview, text='Export results',
                command=self.export_results)
        self.export_button.grid(row=4, column=1)
        
        self.export_name = tk.Entry(self.opview, width=50)
        self.export_name.insert(0, "enter export name")
        self.export_name.grid(row=4, column=2)
        

        self.batch_button = tk.Button(self.opview, text='Batch measure&save all',
                command=self.batch_process)
        self.batch_button.grid(row=5, column=1)
                
        self.batch_name = tk.Entry(self.opview, width=50)
        self.batch_name.insert(0, "batch_name")
        self.batch_name.grid(row=5, column=2)
 

        # Images view: Image looking and ROI selection
        # -------------------------------------------------
        self.imview = tk.LabelFrame(self, text='Images and ROI')
        self.imview.grid(row=1, column=1)

        self.imview_buttons = ButtonsFrame(self.imview,
                ['Exclude image', 'Exclude index'],
                [self.toggle_exclude, lambda: self.toggle_exclude(by_index=True)])
        
        self.imview_buttons.grid(row=1, column=1)


        self.image_slider = tk.Scale(self.imview, from_=0, to=0,
                orient=tk.HORIZONTAL, command=self.change_image)
        
        self.image_slider.grid(row=2, column=1, sticky='NSWE')

        self.images_plotter = CanvasPlotter(self.imview)
        self.images_plotter.grid(row=3, column=1) 
        
        ax = self.images_plotter.ax
        self.excludetext = ax.text(0.5, 0.5, '', transform=ax.transAxes,
                fontsize=24, ha='center', va='center', color='red')



        # Results view: Analysed traces
        # ------------------------------------
        
        self.tabs = Tabs(self, ['Displacement', 'Heatmap'])
        self.tabs.grid(row=1, column=2)
        self.resview = self.tabs.pages[0]
        self.heatview = self.tabs.pages[1]

        #self.resview = tk.LabelFrame(self, text='Results')
        #self.resview.grid(row=1, column=2)
       
        self.results_plotter = CanvasPlotter(self.resview)
        self.results_plotter.grid(row=2, column=1) 
        
        self.heatmap_plotter = CanvasPlotter(self.heatview)
        self.heatmap_plotter.grid(row=2, column=2) 
        
        self.heatmap_slider = tk.Scale(self.heatview, from_=0, to=0,
            orient=tk.HORIZONTAL, command=self.change_heatmap)
        self.heatmap_slider.grid(row=0, column=1, sticky='NSWE')
        
        self.heatmapcap_slider = tk.Scale(self.heatview, from_=0.1, to=100,
            orient=tk.HORIZONTAL, resolution=0.1)
        self.heatmapcap_slider.set(20)
        self.heatmapcap_slider.grid(row=0, column=2, sticky='NSWE') 
        
        self.heatmap_firstcap_slider = tk.Scale(self.heatview, from_=0.1, to=100,
            orient=tk.HORIZONTAL, resolution=0.1)
        self.heatmap_firstcap_slider.set(20)
        self.heatmap_firstcap_slider.grid(row=1, column=2, sticky='NSWE') 
       
        
        self.status = tk.Label(self, text='Nothing to do')
        self.status.grid(row=2, column=1, columnspan=2)

        #self.open_directory(directory='/home/joni/smallbrains-nas1/array1/xray_ESRF2/flattened_ESRF2/fly4/fly4/temp_flattened_head_SI1500/')

    def stop():
        self.exit=True
        if self.movemeter:
            self.movemeter.stop()

    def set_fs(self, fs=None):

        if fs is None:
            fs = simpledialog.askfloat('Imaging frequency (Hz)', 'How many images were taken per second')

        if fs:
            self.fs = fs
            self.fs_button.configure(text='fs = {} Hz'.format(self.fs))


    def open_directory(self, directory=None):
        
        if directory is None:
            try: 
                with open(os.path.join(MOVEDIR, 'last_directory.txt'), 'r') as fp:
                    previous_directory = fp.read().rstrip('\n')
            except FileNotFoundError:
                previous_directory = os.getcwd()

            print(previous_directory)

            if os.path.exists(previous_directory):
                directory = filedialog.askdirectory(title='Select directory with the images', initialdir=previous_directory)
            else:
                directory = filedialog.askdirectory(title='Select directory with the images')
            
            
        if directory:
            if not os.path.isdir(MOVEDIR):
                os.makedirs(MOVEDIR)
            with open(os.path.join(MOVEDIR, 'last_directory.txt'), 'w') as fp:
                fp.write(directory)

            self.folders.append(directory)
            self.folders_listbox.set_selections(self.folders)
            self.folder_selected(directory)

    
    def remove_directory(self):
        
        self.folders.remove(self.current_folder)
        self.folders_listbox.set_selections(self.folders)


    def folder_selected(self, folder):
        '''
        When the user selects a folder from the self.folders_listbox
        '''
        
        self.current_folder = folder

        print('Selected folder {}'.format(folder))

        self.image_fns = [os.path.join(folder, fn) for fn in os.listdir(folder) if fn.endswith('.tiff') or fn.endswith('.tif')]
        self.image_fns.sort()

        self.images = [None for fn in self.image_fns]
        self.mask_image = None

        self.change_image(slider_value=1)
        N_images = len(self.image_fns)
        self.image_slider.config(from_=1, to=N_images)
       
        self.export_name.delete(0, tk.END)
        self.export_name.insert(0, os.path.basename(folder.rstrip('/')))


    def toggle_exclude(self, by_index=False):
        '''
        by_index  If true, toggle exclude for all images with this index
        '''

        indx = int(self.image_slider.get()) - 1
        if by_index:
            fn = indx
        else:
            fn = self.image_fns[indx]

        if fn not in self.exclude_images:
            self.exclude_images.append(fn)
            self.set_status('Removed image {} from the analysis'.format(fn))
        else:
            self.exclude_images.remove(fn) 
            self.set_status('Added image {} back to the analysis'.format(fn))
        
        self.mask_image = None
        self.change_image(slider_value=self.image_slider.get())
        print(self.exclude_images)
        
    
    def recalculate_old(self, directory=None):
        '''
        Using the current settings, recalculate old data by opening the
        zip file and reading image filenames and ROI limits from there.
        '''

        if directory == None:
            directory = filedialog.askdirectory()
            if not directory:
                return None
        
        self.exit = False
        for root, dirs, fns in os.walk(directory):
            
            if self.exit:
                break

            movzip = [fn for fn in os.listdir(root) if fn.startswith('movemeter') and fn.endswith('.zip')]
            
            if movzip:
                settings, filenames, rois, movements = self._load_movzip(os.path.join(root, movzip[0]))
                
                x1, y1 = np.min(rois, axis=0)[0:2]
                x2, y2 = np.max(rois, axis=0)[0:2] + rois[0][3]
                self.set_roi(x1,y1,x2,y2)

                self.folder_selected(os.path.dirname(filenames[0]))
                self.measure_movement()

                self.export_results(batch_name=self.batch_name.get())
                
                print(filenames)
                print(rois)



    def batch_process(self):
        self.exit = False
        for folder in self.folders:
            if self.exit:
                break
            self.folder_selected(folder)
            self.measure_movement()
            self.export_results(batch_name=self.batch_name.get())


    def measure_movement(self):
        if self.image_fns and self.rois:
            print('Started roi measurements')
            
            cores = int(self.cores_slider.get())
            if cores == 1:
                cores = False
            
            self.movemeter = Movemeter(upscale=float(self.upscale_slider.get()),
                    multiprocess=cores, print_callback=self.set_status,
                    **self.movemeter_tickboxes.states)
           
            # Set movemeted data
            images = [self._included_image_fns()]
            print(len(images[0]))
            self.movemeter.set_data(images, [self.rois])
            
            self.results = self.movemeter.measure_movement(0, max_movement=int(self.maxmovement_slider.get()), optimized=True)
            self.plot_results()

            self.calculate_heatmap()
            self.change_heatmap(1)

            print('Finished roi measurements')
        else:
            print('No rois')

    
    def update_grid(self):
        self.set_roi(*self.selection)

    def fill_grid(self):
        self.set_roi(0,0,*reversed(self.images[0].shape))
    
    def set_roi(self, x1,y1,x2,y2):
        self.selection = (x1, y1, x2, y2)
        w = x2-x1
        h = y2-y1
        block_size = self.blocksize_slider.get()
        block_size = (block_size, block_size)
        self.rois = gen_grid((x1,y1,w,h), block_size, step=float(self.overlap_slider.get()))
        
        if len(self.rois) < 10000:
            self.set_status('Plotting all ROIs...')
        else:
            self.set_status('Too many ROIs, plotting only 10 000 first...')
        
        fig, ax = self.images_plotter.get_figax()
        
        # Clear any previous patches
        for patch in self.roi_patches:
            patch.remove()
        self.roi_patches = []

        for roi in self.rois[:10000]:
            patch = matplotlib.patches.Rectangle((float(roi[0]), float(roi[1])),
                    float(roi[2]), float(roi[3]), fill=True, color='red',
                    alpha=0.2)
            self.roi_patches.append(patch)

            ax.add_patch(patch)
        
        self.images_plotter.update()
        print('FInished plotting rois')
        

    def change_image(self, slider_value=None):
        
        image_i = int(slider_value) -1
        print(slider_value)

        if not 0 <= image_i < len(self.image_fns):
            return None

        if self.mask_image is None:
            for i in range(len(self.images)):
                self.images[i] = tifffile.imread(self.image_fns[i])
            
            self.mask_image = np.inf * np.ones(self.images[0].shape)
            
            for image in self.images:
                self.mask_image = np.min([self.mask_image, image], axis=0)


        if self.images[image_i] is None:
            self.images[image_i] = tifffile.imread(self.image_fns[image_i])
        
        
        if image_i in self.exclude_images or self.image_fns[image_i] in self.exclude_images:
            self.excludetext.set_text('EXCLUDED')
        else: 
            self.excludetext.set_text('')

        self.images_plotter.imshow(self.images[image_i]-self.mask_image, roi_callback=self.set_roi, cmap='gray')
        #self.images_plotter.update()

    @staticmethod
    def get_displacements(results):
        return [np.sqrt(np.array(x)**2+np.array(y)**2) for x,y in results]

    def plot_results(self):
        self.results_plotter.ax.clear()
        for x,y in self.results[:50]:
            self.results_plotter.plot(np.sqrt(np.array(x)**2+np.array(y)**2), ax_clear=False, color='red')

    def _included_image_fns(self):
        return [fn for i_fn, fn in enumerate(self.image_fns) if fn not in self.exclude_images and i_fn not in self.exclude_images]
    

    def calculate_heatmap(self):

        self.heatmap_images = []
        
        for i_frame in range(len(self._included_image_fns())):
            if i_frame == 0:
                continue
            image = np.zeros(self.images[0].shape)
            for ROI, (x,y) in zip(self.rois, self.results):
                values = (np.sqrt(np.array(x)**2+np.array(y)**2))
                value = abs(values[i_frame] - values[i_frame-1])
                xx,yy,w,h = ROI
                step = float(self.overlap_slider.get())
                cx = xx+int(round(w/2))
                cy = yy+int(round(h/2))
                #image[yy:yy+h, xx:xx+w] = value
                image[cy-int(step*(h/2)):cy+int(round(step*(h/2))), cx-int(round(step*(w/2))):cx+int(round(step*(w/2)))] = value
            
            if np.max(image) < 0.01:
                image[0,0] = 1
            self.heatmap_images.append(image)

        self.heatmap_slider.config(from_=1, to=len(self.heatmap_images))
        self.heatmap_slider.set(1) 


    def change_heatmap(self, slider_value=None, only_return_image=False):
        if slider_value == None:
            slider_value = int(self.heatmap_slider.get())

        i_image = int(slider_value) - 1
        image = np.copy(self.heatmap_images[i_image])
        
        # Total max value cap
        allframemax = np.max(self.heatmap_images, axis=0)
        image[allframemax > float(self.heatmapcap_slider.get())] = 0
        
        # First value max cap
        firstframemax = np.max(self.heatmap_images[0:3], axis=0)
        image[firstframemax > float(self.heatmap_firstcap_slider.get())] = 0
        
        image = image / float(self.heatmapcap_slider.get())

        if only_return_image:
            return image
        else:
            self.heatmap_plotter.imshow(image, normalize=False)


    def set_status(self, text):
        self.status.config(text=text)
        self.status.update_idletasks()


    def _save_movzip(self, fn):
        
        # Dump GUI settings
        settings = {}
        settings['block_size'] = self.blocksize_slider.get()
        settings['relative_distance'] = self.overlap_slider.get()
        settings['maximum_movement'] = self.maxmovement_slider.get()
        settings['upscale'] = self.upscale_slider.get()
        settings['cpu_cores'] = self.cores_slider.get() 
        settings['export_time'] = str(datetime.datetime.now())
        
        if self.images:
            settings['images_shape'] = self.images[0].shape

        with zipfile.ZipFile(fn, 'w') as savezip:

            with savezip.open('metadata.json', 'w') as fp:
                fp.write(json.dumps(settings).encode('utf-8'))

            # Dump exact used filenames
            self.set_status('Saving used image filenames')
            with savezip.open('image_filenames.json', 'w') as fp:
                fp.write(json.dumps(self._included_image_fns()).encode('utf-8'))

            # Dump ROIs
            self.set_status('Saving ROIs')
            with savezip.open('rois.json', 'w') as fp:
                fp.write(json.dumps(self.rois).encode('utf-8'))

            # Dump analysed movements
            self.set_status('Saving movements')
            with savezip.open('movements.json', 'w') as fp:
                fp.write(json.dumps(self.results).encode('utf-8'))

    def _load_movzip(self, fn):

        with zipfile.ZipFile(fn, 'r') as loadzip:

            # Dump exact used filenames
            with loadzip.open('image_filenames.json', 'r') as fp:
                filenames = json.loads(fp.read())

            # Dump ROIs
            with loadzip.open('rois.json', 'r') as fp:
                rois = json.loads(fp.read())

        return [], filenames, rois, []


    def export_results(self, batch_name=None):

        savename = self.export_name.get()
        zipsavename = savename

        save_root = MOVEDIR
        if batch_name is not None:
            save_root = os.path.join(save_root, 'batch', batch_name)
        
        save_directory = os.path.join(save_root, savename)
        os.makedirs(save_directory, exist_ok=True)
    
        self._save_movzip(os.path.join(save_directory, 'movemeter_{}.zip'.format(zipsavename)))

        with open(os.path.join(save_directory, 'movements_{}.csv'.format(zipsavename)), 'w') as fp:
            writer = csv.writer(fp, delimiter=',')
            
            displacements = self.get_displacements(self.results)
            
            writer.writerow(['time (s)', 'mean displacement (pixels)'] + ['ROI{} displacement (pixels)'.format(k) for k in range(len(displacements))])

            for i in range(len(displacements[0])):
                row = [displacements[j][i] for j in range(len(displacements))]
                row.insert(0, np.mean(row))
                row.insert(0, i/self.fs)
                writer.writerow(row)

        
        slider_i = int(self.image_slider.get())
        self.image_slider.set(int(len(self._included_image_fns()))/2)
        #change_image(slider_value=int(len(self._included_image_fns())/2))

        # Image of the ROIs
        self.set_status('Saving the image view')
        fig, ax = self.images_plotter.get_figax()
        fig.savefig(os.path.join(save_directory, 'movemeter_imageview.jpg'), dpi=400, pil_kwargs={'optimize': True})
        
        self.image_slider.set(slider_i)
        #change_image(slider_value=int(len(self._included_image_fns())/2))
        
        # Image of the result traces
        self.set_status('Saving the results view')
        fig, ax = self.results_plotter.get_figax()
        fig.savefig(os.path.join(save_directory, 'movemeter_resultsview.jpg'), dpi=400, pil_kwargs={'optimize': True})

        # Image of the result traces
        #fig, ax = self.heatmap_plotter.get_figax()
        #fig.savefig(os.path.join(save_directory, 'heatmap_view.jpg'), dpi=600, optimize=True)

        #maxval = np.max(self.heatmap_images)
        #heatmaps = [np.copy(image)/maxval for image in self.heatmap_images]
        
        self.set_status('Saving heatmaps from matplotlib')
        heatmaps = [self.change_heatmap(i+1, only_return_image=True) for i in range(len(self.heatmap_images))]
        
        # Save heatmap images
        #subsavedir = os.path.join(save_directory, 'heatmap_npy')
        #os.makedirs(subsavedir, exist_ok=True)
        #for fn, image in zip(self.image_fns, self.heatmap_images):
        #    np.save(os.path.join(subsavedir, 'heatmap_{}.npy'.format(os.path.basename(fn))), image)

        #subsavedir = os.path.join(save_directory, 'heatmap_matplotlib')
        #os.makedirs(subsavedir, exist_ok=True)
        #for fn, image in zip(self.image_fns, heatmaps):
        #    self.heatmap_plotter.imshow(image, normalize=False)
        #    fig, ax = self.heatmap_plotter.get_figax()
        #    fig.savefig(os.path.join(subsavedir, 'heatmap_{}.jpg'.format(os.path.basename(fn))), dpi=300, optimize=True)

        
        self.set_status('DONE Saving :)')

        # Save heatmap images
        #subsavedir = os.path.join(save_directory, 'heatmap_pillow')
        #os.makedirs(subsavedir, exist_ok=True)
       
        #for fn, image in zip(self.image_fns, heatmaps):
        #    pimage = Image.fromarray(image)
        #    pimage.save(os.path.join(subsavedir, 'heatmap_{}.png'.format(os.path.basename(fn))))

            
          

def main():
    '''
    Initialize tkinter and place the Movemeter GUI
    on the window.
    '''
    root = tk.Tk()
    root.title('Movemeter - Tkinter GUI - {}'.format(__version__))
    gui = MovemeterTkGui(root)
    gui.grid()
    root.mainloop()


if __name__ == "__main__":
    main()
