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
  config.read(os.path.join(root_dir, config_filename))
  pprint(config.sections())
  #if 'control_locations' in config.sections():
  #  for c_type in config['control_locations']:
  #    config['control_locations'][c_type] = config['control_locations'][c_type].split(',')
  return config

#processes plateset from processTecanInput
#goes through wells, if control then check if within deviation from expected val
#return false if any val outside deviation, true if all passed
def checkControls(plateset):

  pos_control_max = float(config['values']['expected_control_value']) + float(config['values']['deviation_from_expected_control_value'])
  pos_control_min = float(config['values']['expected_control_value']) - float(config['values']['deviation_from_expected_control_value'])
  neg_control_max = 0 + float(config['values']['deviation_from_expected_control_value'])
  neg_control_min = 0 - float(config['values']['deviation_from_expected_control_value'])

  for well in plateset:
    if well['WellType'] == 'neg' and (well['avg'] > neg_control_max or well['avg'] < neg_control_min):
      return False
    elif well['WellType'] == 'pos' and (well['avg'] > pos_control_max or well['avg'] < pos_control_min):
      return False

  return True

def wellKey(well):
  well_split = re.search(r'(^[A-Z]{1})([0-9]{2})$', well)
  return '{num}{letter}'.format(num=well_split.group(2), letter=well_split.group(1))

#process the plateset (data from processTecanInput)
#return a dict containing:
# - processed values (average of plate_1 (OD1) and plate_2 (OD2), or the lower if ratio bounds are exceeded
# - ratios of plate_1/plate_2 values
# - which value used ('decision') (1 = plate_1, 2 = plate_2, 3 = average)
# - abort (0/1) set to 1 if more than limit_acceptable_bigtime_flyers are found
# - ratio_mean and ratio_sd for all ratios (excluding 'bigtime flyers' i.e. decision 1 or 2)
def processPlateset(plateset):
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

  for well in plateset:
    print(well)
    well_no = well['WellNo']
    well_name = well['WellName']
    ratio = well['ratio']
    out_value = None
    decision = None
    well_type = well['WellType']

    if float(config['values']['flyer_lower']) > well['ratio'] or well['ratio'] > float(config['values']['flyer_upper']):
      if well['OD1'] < well['OD2']:
        out_value = well['OD1']
        decision = 1
      else:
        out_value = well['OD2']
        decision = 2
      flyers_found += 1
    else:
      out_value = well['avg']
      decision = 3
    simple_output.append({'wellNo': well_no, 'select': decision, 'abort': 0 if decision == 3 else 1, 'wellName': well_name, 'wellType': well_type, 'OD1': well['OD1'], 'OD2': well['OD2']})
    calculated_o['values'][well_name] = out_value
    calculated_o['decision'][well_name] = decision
    calculated_o['ratios'][well_name] = ratio
    if flyers_found > int(config['values']['limit_acceptable_bigtime_flyers']):
      calculated_o['abort'] = 1

  #pprint(calculated_o)
  #do mean and sd of ratios for non-bigtime_flyers (decision = 3)
  usable_values = []
  for well, ratio in calculated_o['ratios'].items():
    if calculated_o['decision'][well_name] == 3:
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
  # (normally C:\Tecan\Pegasus Data\Autohandler\processed\[%d%m%Y.%H%M%S]\[platename].txt)
  ##
  from datetime import datetime
  now = datetime.now()
  processed_file_dir = '{now.day:0>2}{now.month:0>2}{now.year}.{now.hour:0>2}{now.minute:0>2}{now.second:0>2}'.format(now = now) 
  #make output dir if not exists
  try:
    os.stat(os.path.join(config['base']['processed_output_location'], processed_file_dir))
  except:
    os.mkdir(os.path.join(config['base']['processed_output_location'], processed_file_dir))
  
  processed_file = open(os.path.join(config['base']['processed_output_location'], processed_file_dir, '{platename}.txt'.format(platename=platename)), 'w')

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

def processTecanInput(input_filename):
  try:
    input_file = open(input_filename, 'r', encoding='latin-1')
    
    fields = []
    data = []
    line_no = 1

    for line in input_file:
      #clean ends of line before splitting
      #print(line)
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
          try:
            line_dict[field_index[1]] = line_data[field_index[0]]
          except IndexError as e:
            print(fields)
            print(line_data)
            print(line_dict)
        data.append(line_dict)
      line_no += 1

    #calculate averages and ratios
    for well in data:
      well['OD1'] = float(well['OD1'])
      well['OD2'] = float(well['OD2'])
      well['avg'] = (well['OD1'] + well['OD2']) / 2
      try:
        well['ratio'] = well['OD1'] / well['OD2']
      except ZeroDivisionError:
        well['ratio'] = 0

    return data

  except IOError as e:
    print("Error opening or reading input file {input_filename}".format(input_filename=input_filename))
    print(str(e))
             
if __name__ == '__main__':
  print(os.getcwd())
  parser = argparse.ArgumentParser(description='Process Tecan export .txt conentration files to return average values and bigtime flyers')
  parser.add_argument('--config', dest='config_filename', action='store', help='.ini configuration filename. This must be in the folder "ini_file"')
  global args
  args = parser.parse_args()
  global config
  config = loadConfig('base_config.ini')
  pprint(config.sections())
  pprint(args.config_filename)
  config = loadConfig(args.config_filename, config)

  #get file
  #this should be in C:\ProgramData\Tecan\Pegasus\ALSPAC\AutoHandler\
  #named as [platename].txt
  #as Tecan calls it the 'export' file we'll stick with that
  #our output will be called 'Import.txt' as per current output
  platename = None
  print(config['base']['tecan_export_location'])
  for files in next(os.walk(config['base']['tecan_export_location'])):
    for filename in files:
      namematch = re.search(r'^([a-zA-Z_\-]+?[0-9]+?)(\.txt$)', filename)
      if namematch is not None:
        tecan_export_file = os.path.join(config['base']['tecan_export_location'], filename)
        platename = namematch.group(1)
    #we don't want to go into subdirs, so break after doing files
    #break
  
  #setup platesets - this will contain the data processed from the source asc files
  try:
    print('Tecan export file:')
    pprint(tecan_export_file)
  except NameError:
    print('Unable to find Tecan export file')
    exit(1)
  plateset = processTecanInput(tecan_export_file)
  controls_ok = checkControls(plateset)
  output = processPlateset(plateset)
  exportFiles(output)
  #pprint(output)
  exit(0)






