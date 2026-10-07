"""Validate the immutable sheet/cell Unicode map without reading Office XML."""
import re

def address(value):
 if type(value) is not str:raise ValueError('XLSX_LOCATION_INVALID')
 m=re.fullmatch(r'([A-Z]{1,3})([1-9][0-9]{0,6})',value)
 if not m:raise ValueError('XLSX_LOCATION_INVALID')
 col=0
 for char in m[1]:col=col*26+ord(char)-64
 row=int(m[2])
 if col>16384 or row>1048576:raise ValueError('XLSX_LOCATION_INVALID')
 return row,col

def valid_name(name):
 return type(name) is str and 1<=len(name)<=31 and not re.search(r'[\x00-\x1f\x7f:/\\?*\[\]]',name) and not name.startswith("'") and not name.endswith("'")

def validate_xlsx_locations(locations,character_length):
 if type(locations) is not list or not 1<=len(locations)<=2010:raise ValueError('XLSX_LOCATION_INVALID')
 end=-2;sheet=0;name=None;names=set();previous=(0,0);cells=0
 for loc in locations:
  if type(loc) is not dict or loc.get('kind') not in ('sheet','cell'):raise ValueError('XLSX_LOCATION_INVALID')
  keys={'kind','sheet_index','sheet_name','start','end'}|({'cell'} if loc['kind']=='cell' else set())
  if set(loc)!=keys or any(type(loc[k]) is not int for k in ('sheet_index','start','end')) or not valid_name(loc['sheet_name']):raise ValueError('XLSX_LOCATION_INVALID')
  if loc['start']!=end+2 or not loc['start']<loc['end']<=character_length:raise ValueError('XLSX_LOCATION_INVALID')
  end=loc['end']
  if loc['kind']=='sheet':
   if loc['sheet_index']!=sheet+1 or loc['sheet_index']>10 or loc['sheet_name'].casefold() in names:raise ValueError('XLSX_LOCATION_INVALID')
   sheet+=1;name=loc['sheet_name'];names.add(name.casefold());previous=(0,0)
  else:
   order=address(loc['cell']);cells+=1
   if loc['sheet_index']!=sheet or loc['sheet_name']!=name or order<=previous or cells>2000:raise ValueError('XLSX_LOCATION_INVALID')
   previous=order
 if end!=character_length or not cells:raise ValueError('XLSX_LOCATION_INVALID')
