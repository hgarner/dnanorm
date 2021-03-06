import csv
import re
import os
import sys
import shutil
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

# processes plateset from processTecanInput
# goes through wells, if control then check if within deviation 
# from expected val
# return false if any val outside deviation, true if all passed
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

# process the plateset (data from processTecanInput)
# return a dict containing:
# - processed values (average of plate_1 (OD1) and plate_2 (OD2), 
#   or the lower if ratio bounds are exceeded
# - ratios of plate_1/plate_2 values
# - which value used ('decision') (1 = plate_1, 2 = plate_2, 3 = average)
# - abort (0/1) set to 1 if more than limit_acceptable_bigtime_flyers are found
# - ratio_mean and ratio_sd for all ratios (excluding 'bigtime flyers' i.e. decision 1 or 2)
def processPlateset(plateset):
  # set up output dict
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
    
    # if well_type is empty, set decision to 0, otherwise process as normall
    if well_type == '':
      out_value = ''
      decision = 0
    else:
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
    simple_output.append({'wellNo': well_no, 'select': decision, 'abort': 0 if decision == 3 or decision == 0 else 1, 'wellName': well_name, 'wellType': well_type, 'OD1': well['OD1'], 'OD2': well['OD2']})
    calculated_o['values'][well_name] = out_value
    calculated_o['decision'][well_name] = decision
    calculated_o['ratios'][well_name] = ratio
    if flyers_found > int(config['values']['limit_acceptable_bigtime_flyers']):
      calculated_o['abort'] = 1

  # do mean and sd of ratios for non-bigtime_flyers (decision = 3)
  usable_values = []
  for well, ratio in calculated_o['ratios'].items():
    if calculated_o['decision'][well_name] == 3:
      pprint(well_name)
      pprint(ratio)
      usable_values.append(ratio)
  #if len(usable_values) > 0:
  #  calculated_o['ratio_mean'] = mean(usable_values)
  #  calculated_o['ratio_sd'] = stdev(usable_values)
  calculated_o['ratio_mean'] = mean(usable_values)
  calculated_o['ratio_sd'] = stdev(usable_values)

  return {'simple': simple_output, 'calculated': calculated_o, 'abort': calculated_o['abort']}

# export the output data to dir [ddmmyyyy.hhmmss] in config['base']['processed_output_location']
def exportFiles(output_data):
  ##
  #output the decision data to Import.txt in output_location
  ##
  decision_file = open(os.path.join(config['base']['output_location'], 'Import.txt'), 'w')
  ##
  # output the processed data to config['base']['processed_output_location']
  # (normally C:\Tecan\Pegasus Data\Autohandler\processed\[%d%m%Y.%H%M%S]\[platename].txt)
  ##
  from datetime import datetime
  now = datetime.now()
  processed_file_dir = '{now.day:0>2}{now.month:0>2}{now.year}.{now.hour:0>2}{now.minute:0>2}{now.second:0>2}'.format(now = now) 
  # set config['process_file_dir']
  config['base']['processed_file_dir'] = processed_file_dir
  # make output dir if not exists
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

# process the raw input file
# return a list with element for each line
# containing dicts of {fieldname: fieldvalue, ...} 
def processTecanInput(input_filename):
  try:
    input_file = open(input_filename, 'r', encoding='latin-1')
    
    fields = []
    data = []
    line_no = 1

    for line in input_file:
      #clean ends of line before splitting
      line = re.sub(r'^<(.*?)>\n$', r'\1', line)
      line_data = re.split(r'><', line)
      line_dict = {}

      if line_no == 1:
        #if line 1 we use this as field names
        fields = deepcopy(line_data)
      else:
        #otherwise assign data to dict using fields and append to data
        for field_index in enumerate(fields):
          try:
            line_dict[field_index[1]] = line_data[field_index[0]]
          except IndexError as e:
            print('Error processing input file')
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

# clean any residual files and move the inputfile 
# to config['base']['processed_file_dir'] 
# (usually processed/[datetime])
def cleanupFiles(tecan_export_file, *args):
  # currently only needs to move tecan_export_file
  # additional files may be added as *args 
  # (tecan_export_location is prepended to filename)
  # try copying the file first to processed_output_location
  # if this fails (output location doesn't exist), assume script has errored
  # in any case, then remove the tecan_export_file
  try:
    shutil.copy(tecan_export_file, os.path.join(config['base']['processed_output_location'], config['base']['processed_file_dir'], os.path.split(tecan_export_file)[1]))
  except Exception as e:
    print('Error copying Tecan export file.')
    
  try:
    os.remove(tecan_export_file)
  except OSError:
    print('Unable to remove Tecan export file. Already done?')
  except:
    print('Error removing Tecan export file')
    
  for filename in args:
    try:
      os.remove(os.path.join(config['base']['tecan_export_location'], filename))
    except OSError:
      print('Unable to remove additional file {filename}. File may not exist.'.format(filename=filename))
    except:
      print('Error removing file {filename}.'.format(filename=filename))
             
# run from command line
# - parse the provided arg for config file
# - load the config file to get input/output locations etc
# - process the input file to get values for each plate well
# - process the dataset to get averages and decisions for each well,
#   plus abort flag
# - write output to relevant locations
# - cleanup input file(s)
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

  # get file
  # this should be in C:\ProgramData\Tecan\Pegasus\ALSPAC\AutoHandler\
  # named as [platename].txt
  # as Tecan calls it the 'export' file we'll stick with that
  # our output will be called 'Import.txt' as per current output
  platename = None
  print(config['base']['tecan_export_location'])
  for files in next(os.walk(config['base']['tecan_export_location'])):
    for filename in files:
      namematch = re.search(r'^([a-zA-Z_\-]+?[0-9]+?)(\.txt$)', filename)
      if namematch is not None:
        tecan_export_file = os.path.join(config['base']['tecan_export_location'], filename)
        platename = namematch.group(1)
  
  # setup platesets - this will contain the data processed from the source asc files
  try:
    print('Tecan export file:')
    pprint(tecan_export_file)
  except NameError:
    print('Unable to find Tecan export file')
    exit(1)

  try: 
    plateset = processTecanInput(tecan_export_file)

    # check the controls are ok
    controls_ok = checkControls(plateset)

    # generate the output by processing the plateset generated from the 
    # tecan_export_file
    output = processPlateset(plateset)
    pprint(output)

    # output the data - Import.txt (decision) to processed_output_location,
    # the results of the processing (values) to output_location
    exportFiles(output)

    # cleanup files (usually just those copied to tecan_export_location)
    cleanupFiles(tecan_export_file)
    exit(0)
  except Exception as e:
    # on error, we still need to cleanup file copied to tecan_export_location
    cleanupFiles(tecan_export_file)
    # print the error and exit
    print(e)
    exit(1)







