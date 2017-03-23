import csv
import re
import os
import sys
from statistics import mean, stdev
import configparser
import argparse
from copy import deepcopy
from pprint import pprint

def loadConfig(config_filename = 'config.ini', config = None):
  root_dir = os.getcwd()
  if config is None:
    config = configparser.ConfigParser()
  config.read(os.path.join(config_filename))
  pprint(config.sections())
  #if 'control_locations' in config.sections():
  #  for c_type in config['control_locations']:
  #    config['control_locations'][c_type] = config['control_locations'][c_type].split(',')
  return config

def loadFiles(file_1, file_2):
  plate_1 = PlateSet()
  plate_2 = PlateSet()
  plate_1.processCsv(file_1)
  plate_2.processCsv(file_2)
  return {'plate_1': plate_1, 'plate_2': plate_2}

def checkControls(platesets):
  if 'plate_1' not in platesets.keys() or 'plate_2' not in platesets.keys():
    raise KeyError('Missing plate_1 or plate_2 from plates dict')
  
  control_max = float(config['values']['expected_control_value']) + float(config['values']['deviation_from_expected_control_value'])
  control_min = float(config['values']['expected_control_value']) - float(config['values']['deviation_from_expected_control_value'])

  for location in config['control_locations']['neg'].split(',') + config['control_locations']['pos'].split(','):
    if control_min > platesets['plate_1'].plates[0][location] > control_max:
      return False
    elif control_min > platesets['plate_2'].plates[0][location] > control_max:
      return False

  return True

def wellKey(well):
  well_split = re.search(r'(^[A-Z]{1})([0-9]{2})$', well)
  return '{num}{letter}'.format(num=well_split.group(2), letter=well_split.group(1))

#process the platesets (class PlateSet)
#only uses plateset[n].plate[0]. others are ignored
#return a dict containing:
# - processed values (average of plate_1 and plate_2, or the lower if ratio bounds are exceeded
# - ratios of plate_2/plate_1 values
# - which value used ('decision') (1 = plate_1, 2 = plate_2, 3 = average)
# - abort (0/1) set to 1 if more than limit_acceptable_bigtime_flyers are found
# - ratio_mean and ratio_sd for all ratios (excluding 'bigtime flyers' i.e. decision 1 or 2)
def processPlatesets(platesets):
  if 'plate_1' not in platesets.keys() or 'plate_2' not in platesets.keys():
    raise KeyError('Missing plate_1 or plate_2 from plates dict')
  
  #set up output dict
  calculated_o = {
    'values': {},
    'ratios': {},
    'decision': {},
    'abort': 0,
    'ratio_mean': None,
    'ratio_sd': None
    }

  #simple output with no processed values
  simple_output = []
  
  flyers_found = 0

  wells = [key for key in platesets['plate_1'].plates[0].keys()]
  wells.sort(key=wellKey)

  for well_loc in enumerate(wells):
    well_no = well_loc[0]
    well = well_loc[1]
    p1_value = platesets['plate_1'].plates[0][well]
    p2_value = platesets['plate_2'].plates[0][well]
    out_value = None
    decision = None
    well_type = 'Sample'
    if p1_value == '' and p2_value == '':
      well_type = ''
    if well in config['control_locations']['neg']:
      well_type = 'neg'
    elif well in config['control_locations']['pos']:
      well_type = 'pos'

    try:
      ratio = p2_value/p1_value
    except ZeroDivisionError:
      ratio = 0
    if float(config['values']['flyer_lower']) > ratio or ratio > float(config['values']['flyer_upper']):
      if p1_value < p2_value:
        out_value = p1_value
        decision = 1
      else:
        out_value = p2_value
        decision = 2
      flyers_found += 1
    else:
      out_value = (p1_value + p2_value)/2
      decision = 3
    simple_output.append({'wellNo': well_no, 'select': decision, 'abort': 0 if decision == 3 else 1, 'wellName': well, 'wellType': well_type, 'OD1': p1_value, 'OD2': p2_value})
    calculated_o['values'][well] = out_value
    calculated_o['decision'][well] = decision
    calculated_o['ratios'][well] = ratio
    if flyers_found > int(config['values']['limit_acceptable_bigtime_flyers']):
      calculated_o['abort'] = 1

  pprint(calculated_o)
  #do mean and sd of ratios for non-bigtime_flyers (decision = 3)
  usable_values = []
  for well, ratio in calculated_o['ratios'].items():
    if calculated_o['decision'][well] == 3:
      usable_values.append(ratio)
  calculated_o['ratio_mean'] = mean(usable_values)
  calculated_o['ratio_sd'] = stdev(usable_values)

  #return calculated_o
  return {'simple': simple_output, 'calculated': calculated_o, 'abort': calculated_o['abort']}

def exportFiles(output_data):
  ##
  #output the decision data to Import.txt in output_location
  ##
  decision_file = open(os.path.join(config['base']['output_location'], 'Import.txt'), 'w')
  ##
  # output the processed data to config['processed_output_location']
  # (normally C:\Tecan\Pegasus Data\Autohandler\PROCESSED\[%m%d%Y.%I%M%S %p]\[platename].txt)
  ##
  processed_file = open(os.path.join(config['base']['processed_output_location'], '{platename}.txt'.format(platename=platename)), 'w')

  decision_file.write('<wellNo><select><abort>\n')
  abort_count = 0
  for sample in output_data['simple']:
    decision_file.write('<{well_no}><{select}><{abort}>\n'.format(well_no=sample['wellNo'], select=sample['select'], abort=sample['abort']))
  decision_file.write('<>\nabort={abort}'.format(abort=output_data['abort']))
  decision_file.close()

  processed_file.write('<wellNo><wellName><wellType><OD1><OD2>\n')
  for sample in output_data['simple']:
    processed_file.write('<{well_no}><{well_name}><{well_type}><{od_1}><{od_2}>\n'.format(well_no=sample['wellNo'], well_name=sample['wellName'], well_type=sample['wellType'], od_1=sample['OD1'], od_2=sample['OD2']))
  processed_file.close()

class PlateSet:
  
  def __init__(self):
    self.plate_cols = 12
    self.plate_rows = 8
    self.plate_start_chars = '<>'
    self.csv_delim = '\t'
    self.plates = []
    self.start_metadata = []
    self.end_metadata = []
    self.filename = None

  def processCsv(self, csv_file):
    csv_file = open(csv_file, 'r', encoding='latin-1')
    self.filename = csv_file

    with csv_file:
      reader = csv.reader(csv_file, delimiter=self.csv_delim)
      plate = None
      plate_row = 0
      for line in reader:
        if plate is None and line[0] != self.plate_start_chars:
          if len(self.plates) == 0:
            #we haven't started a plate yet, so stick this data in self.start_metadata
            self.start_metadata.append('\t'.join(line))
          else:
            #this assumes that there's no metadata between plates. if this is not so, this will include it in the end_metadata.
            self.end_metadata.append('\t'.join(line))
        if plate_row > self.plate_rows:
          #if we've filled the plate, append copy to self.plates and reset
          self.plates.append(deepcopy(plate))
          plate = None
          plate_row = 0
        if line[0] == self.plate_start_chars:
          #if this is the start a a new plate, reset plate and row to beginning
          plate = {}
          plate_row = 1
          continue
        elif plate is not None:
          if len(line) < self.plate_cols:
            #do we have enough columns?
            if plate_row == 1 and len(plate.keys()) == 0:
              #skip as non-plate data
              continue
            else:
              #otherwise we have a problem
              raise ValueError('Not enough colums in row {plate_row}, plate {plate_no}'.format(plate_row=plate_row, plate_no=len(self.plates)))
          if len(line) > self.plate_cols:
            #we might have too many columns
            #if the last is empty and we only have a single value more than self.plate_cols 
            #(note that the first col is the row label), we can ignore
            #todo add option to turn this off
            if line[-1] == '' and len(line) == self.plate_cols + 2:
              line = line[:-1]
            else:
              #otherwise we have a problem - too many columns and/or the last is not empty
              raise ValueError('Too many colums in row {plate_row}, plate {plate_no}'.format(plate_row=plate_row, plate_no=len(self.plates)))
          for well in enumerate(line):
            if well[0] != 0:
              location = '{row}{col:02}'.format(row=line[0], col=well[0])
              try:
                #add data to plate location 
                #convert to float
                plate[location] = float(well[1])
              except ValueError:
                #if float conversion fails, try int
                #possibly not ideal as we'll have a mix of types
                try:
                  plate[location] = int(well[1])
                except ValueError:
                  plate[location] = well[1]
              
          plate_row += 1

              
    return self.plates

def processTecanInput(input_filename):
  try:
    input_file = open(input_filename, 'r', encoding='latin-1')
    
    fields = []
    data = []
    line_no = 1

    for line in input_file:
      #clean ends of line before splitting
      print(line)
      line = re.sub(r'^<(.*?)>\n$', r'\1', line)
      line_data = re.split(r'><', line)
      line_dict = {}
      #for field in line_data:
      #  field = re.sub(r'^[<]{0,1}(.*?)[>]{0,1}[\n]{0,1}$', r'\1', field)

      #if input_file.tell() == 1:
      if line_no == 1:
        #if line 1 we use this as field names
        fields = deepcopy(line_data)
      else:
        #otherwise assign data to dict using fields and append to data
        for field_index in enumerate(fields):
          line_dict[field_index[1]] = line_data[field_index[0]]
        data.append(line_dict)
      line_no += 1

    return data
  except IOError as e:
    print("Error opening or reading input file {input_filename}".format(input_filename=input_filename))
    print(str(e))
             
if __name__ == '__main__':
  print(os.getcwd())
  parser = argparse.ArgumentParser(description='Process .asc concentration files to return average values and bigtime flyers')
  parser.add_argument('--config', dest='config_filename', action='store', help='.ini configuration filename. This must be in the folder "ini_file"')
  global args
  args = parser.parse_args()
  global config
  config = loadConfig('/home/edzhg/repos/dnanorm/base_config.ini')
  pprint(args.config_filename)
  config = loadConfig(args.config_filename, config)


  #get files
  #these should just be the two in C:\ProgramData\Tecan\Pegasus\ALSPAC\AutoHandler\asc
  platename = None
  print(config['base']['asc_location'])
  for root, dirs, files in os.walk(config['base']['asc_location']):
    for filename in files:
      namematch = re.search(r'^([a-z0-9A-Z_\-]+?)(_2){0,1}(\.asc$)', filename)
      if namematch is not None:
        if namematch.group(2) is None and namematch.group(3) is not None:
          file_1 = os.path.join(root, filename)
          platename_1 = namematch.group(1)
        elif namematch.group(2) == '_2':
          file_2 = os.path.join(root, filename)
          platename_2 = namematch.group(1)
  
  if platename_1 != platename_2:
    raise ValueError('Platenames of asc files do not match. Are there more than two .asc files present?')
  else:
    platename = platename_1
  #setup platesets - this will contain the data processed from the source asc files
  platesets = loadFiles(file_1, file_2)
  controls_ok = checkControls(platesets)
  output = processPlatesets(platesets)
  exportFiles(output)
  pprint(output)






