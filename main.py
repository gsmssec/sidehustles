import os
import sys
import time
import random
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import requests
import json
import re   
import datetime
import pytz
import logging
import sqlite3
import hashlib



print("Hello " + input("Enter your name: ") + "!")
var1  = input("Enter a string:")

print("The length of the string is :" + str(len(var1)))

if len(var1) > 5:
    print("The string is longer than 5 characters.")
else:
    print("The string is 5 characters or shorter.")
    
