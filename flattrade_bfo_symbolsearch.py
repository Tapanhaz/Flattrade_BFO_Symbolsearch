# -*- coding: utf-8 -*-
"""
    :: Description :: Search scrips in flattrade bfo symbolmaster.
    :: License :: MIT
    :: Author :: Tapan Hazarika
    :: Created :: On Thursday October 28, 2023
"""
__author__ = "Tapan Hazarika"
__license__ = "MIT"

import os
import logging
import requests
import polars as pl
from datetime import datetime
from functools import lru_cache
from typing import Literal, Union


#logging.basicConfig(level=logging.DEBUG)
logging.getLogger(__name__)

class FlattradeBFO:
    BFO_BASE = "https://pidata.flattrade.in/scripmaster/json"
    BFO_IDX = f"{BFO_BASE}/bfoidx"
    BFO_STK = f"{BFO_BASE}/bfostk"

    SENSEX50 = "SENSEX50"
    SENSEX = "SENSEX" 
    BANKEX = "BANKEX"

    def __init__(
                self,
                master: Literal["idx", "stk", "all"]= "idx",
                hard_refresh: bool= False
                ) -> None:
        self.master = master
        self.hard_refresh = hard_refresh

        self.path = os.path.dirname(__file__)
        self.current_date = datetime.now().date()

        if self.hard_refresh:
            self.load_master.cache_clear()
        self.load_master()

    def is_latest(self, filepath: os.path) -> bool:
        file_time = datetime.fromtimestamp(os.path.getmtime(filepath)).date()
        logging.info("File modify time :: {}".format(file_time))
        return file_time == self.current_date
    
    def download_master(self, url: str) -> pl.DataFrame:
        try:
            response = requests.get(url) 
            response.raise_for_status()
            if response.status_code == 200:
                df = pl.from_records(data = response.json()["data"],
                                     schema= {
                                            "exchange" : pl.Utf8,
                                            "token" : pl.Utf8,
                                            "lotsize" : pl.Utf8,
                                            "symbol" : pl.Utf8,
                                            "tradingsymbol" : pl.Utf8,
                                            "expiry" : pl.Utf8,
                                            "instrument" : pl.Utf8,
                                            "optiontype" : pl.Utf8,
                                            "strike" : pl.Utf8
                                        }
                                    )
                #print(df)
                return df
        except (requests.exceptions.RequestException, Exception) as e:
            logging.debug("Error Downloading : {} :: {}".format(url, e))
            return pl.DataFrame()
    
    def load_master_from_file(self, filepath: os.path)-> pl.DataFrame:
        df = pl.read_csv(source= filepath,
                         dtypes= {
                                "exchange" : pl.Utf8,
                                "token" : pl.Utf8,
                                "lotsize" : pl.Utf8,
                                "symbol" : pl.Utf8,
                                "tradingsymbol" : pl.Utf8,
                                "expiry" : pl.Utf8,
                                "instrument" : pl.Utf8,
                                "optiontype" : pl.Utf8,
                                "strikeprice" : pl.Utf8,
                                "strike" : pl.Utf8
                            }
                        )
        return df
    
    def check_and_load_data(self, url: Union[str, tuple], filepath= os.path)-> pl.DataFrame:
        if isinstance(url, str):
            if os.path.exists(filepath):
                if not self.is_latest(filepath):
                    df = self.download_master(url)
                    if df.is_empty():
                        logging.info("Download failed. Using Old SymbolMaster.")
                        df = self.load_master_from_file(filepath)
                    else:
                        df = self.prepare_data(df)
                        if not df.is_empty():
                            df.write_csv(filepath)
                else:
                    if self.hard_refresh:
                        df = self.download_master(url)
                        df = self.prepare_data(df)
                        if not df.is_empty():
                            df.write_csv(filepath)
                    else:
                        df = self.load_master_from_file(filepath)
            else:
                df = self.download_master(url)
                df = self.prepare_data(df)
                if not df.is_empty():
                    df.write_csv(filepath)

        elif isinstance(url, tuple):
            if os.path.exists(filepath):
                if not self.is_latest(filepath):
                    df_idx = self.download_master(url[0])
                    df_stk = self.download_master(url[1])
                    if df_idx.is_empty() or df_stk.is_empty():
                        logging.info("Download failed. Using Old SymbolMaster.")
                        df = self.load_master_from_file(filepath)
                    else:
                        try:
                            df = pl.concat([df_idx, df_stk])
                            df = self.prepare_data(df)
                            if not df.is_empty():
                                df.write_csv(filepath)
                        except pl.ShapeError as e:
                            logging.debug("Error Concating :: {}".format(e))
                else:
                    if self.hard_refresh:
                        df_idx = self.download_master(url[0])
                        df_stk = self.download_master(url[1])
                        try:
                            df = pl.concat([df_idx, df_stk])
                            df = self.prepare_data(df)
                            if not df.is_empty():
                                df.write_csv(filepath)
                        except pl.ShapeError as e:
                            logging.debug("Error Concating :: {}".format(e))
                                                
                    else:
                        df = self.load_master_from_file(filepath)
            else:
                df_idx = self.download_master(url[0])
                df_stk = self.download_master(url[1])
                try:
                    df = pl.concat([df_idx, df_stk])
                    df = self.prepare_data(df)
                    if not df.is_empty():
                        df.write_csv(filepath)
                except pl.ShapeError as e:
                    logging.debug("Error Concating :: {}".format(e))
        return df
    
    @lru_cache(maxsize=None)
    def load_master(self)-> pl.DataFrame:
        idx_file = os.path.join(self.path, "bfo_idx_mod.csv")
        stk_file = os.path.join(self.path, "bfo_stk_mod.csv")
        bfo_file = os.path.join(self.path, "bfo_mod.csv")

        if self.master == "idx":
            df = self.check_and_load_data(url= self.BFO_IDX, filepath= idx_file)
        elif self.master == "stk":
            df = self.check_and_load_data(url= self.BFO_STK, filepath= stk_file)
        elif self.master == "all":
            df = self.check_and_load_data(url= (self.BFO_IDX, self.BFO_STK), filepath= bfo_file)
        return df

    def prepare_data(self, dataframe: pl.DataFrame)-> pl.DataFrame: 

        df = dataframe.lazy().drop(
                                "symbol"
                                ).with_columns(
                                    pl.when(
                                        (pl.col("instrument") == "FUTIDX") 
                                        | 
                                        (pl.col("instrument") == "OPTIDX")
                                            ).then(
                                                pl.when(
                                                    pl.col("tradingsymbol").str.contains(
                                                        self.SENSEX50
                                                        )
                                                    ).then(
                                                        pl.lit(self.SENSEX50)
                                                        ).otherwise(
                                                            pl.when(
                                                                pl.col("tradingsymbol").str.contains(
                                                                        self.SENSEX
                                                                        )
                                                                    ).then(
                                                                        pl.lit(self.SENSEX)
                                                                        ).otherwise(
                                                                            pl.when(
                                                                                pl.col("tradingsymbol").str.contains(
                                                                                        self.BANKEX
                                                                                        )
                                                                                    ).then(
                                                                                        pl.lit(
                                                                                            self.BANKEX
                                                                                            )
                                                                                        )
                                                                                    )
                                                                                )
                                                                            ).otherwise(
                                                                                pl.when(
                                                                                    (pl.col("instrument")== "FUTSTK")
                                                                                    |
                                                                                    (pl.col("instrument")== "OPTSTK")
                                                                                            ).then(
                                                                                                pl.col("tradingsymbol").str.extract(
                                                                                                        pattern= r'^(.*?)(\d)'
                                                                                                        )
                                                                                                    )
                                                                                                ).alias(
                                                                                                    "symbol"
                                                                                                    )
                                                                                                ).with_columns(
                                                                                                    pl.when(
                                                                                                        (pl.col("instrument")== "OPTSTK")
                                                                                                        |
                                                                                                        (pl.col("instrument")== "OPTIDX")
                                                                                                                ).then(
                                                                                                                    pl.col(
                                                                                                                        "tradingsymbol"
                                                                                                                        ).str.split(
                                                                                                                            by= pl.col("symbol")
                                                                                                                            ).list.get(1).str.extract(
                                                                                                                                pattern= r'^.{5}(.*).{2}$'
                                                                                                                                ).alias("strikeprice")
                                                                                                                                )
                                                                                                                            ).with_columns(
                                                                                                                                pl.col(
                                                                                                                                    "strikeprice"
                                                                                                                                    ).fill_null(0)
                                                                                                                                ).select(
                                                                                                                                    [
                                                                                                                                        "exchange",
                                                                                                                                        "token",
                                                                                                                                        "lotsize", 
                                                                                                                                        "symbol",
                                                                                                                                        "tradingsymbol",
                                                                                                                                        "expiry",
                                                                                                                                        "instrument",
                                                                                                                                        "optiontype",
                                                                                                                                        "strikeprice",
                                                                                                                                        "strike"
                                                                                                                                        ]
                                                                                                                                    ).collect()
        return df
    
    def get_expiry(
            self,
            symbol: str=None,
            tradingsymbol: str=None,
            instrument: Literal["FUTIDX", "FUTSTK", "OPTIDX", "OPTSTK"]= "OPTIDX",
            expirytype: Literal["near", "next", "far", "all"]= "near"
            )-> Union[str, list]:
        df = self.load_master()
        try:
            if symbol and not tradingsymbol:
                all_expiry= df.lazy().select(
                                            ["symbol", "expiry","instrument"]
                                        ).filter(
                                            (pl.col("symbol") == symbol.upper())
                                            &
                                            (pl.col("instrument") == instrument)

                                        ).with_columns(
                                            pl.col("expiry").str.to_date(format= "%d-%b-%Y")
                                        ).select(
                                            "expiry"
                                        ).unique().sort(
                                            by="expiry"
                                            ).with_columns(
                                                pl.col("expiry").dt.strftime(format= "%d-%b-%Y").str.to_uppercase()
                                            ).collect()
            elif tradingsymbol:
                all_expiry= df.lazy().select(
                                            ["tradingsymbol", "expiry"]
                                        ).filter(
                                            (pl.col("tradingsymbol") == tradingsymbol.upper())
                                        ).with_columns(
                                            pl.col("expiry").str.to_date(format= "%d-%b-%Y")
                                        ).select(
                                            "expiry"
                                        ).unique().sort(
                                            by="expiry"
                                            ).with_columns(
                                                pl.col("expiry").dt.strftime(format= "%d-%b-%Y").str.to_uppercase()
                                            ).collect()
            if expirytype == "near":
                return all_expiry.item(0,0)
            elif expirytype == "next":
                return all_expiry.item(1,0)
            elif expirytype == "far":
                return all_expiry.item(2,0)
            elif expirytype == "all":
                return all_expiry.to_series().to_list()
        except (IndexError, Exception) as e:
            logging.debug("Error Fetching Expiry :: {}".format(e)) 
    
    def get_tradingsymbol(
                    self,
                    symbol: str,
                    instrument: Literal["FUTIDX", "FUTSTK", "OPTIDX", "OPTSTK"],
                    expiry: str,
                    optiontype: str= "XX",        
                    strikeprice: Union[int, str]= 0                       
                    )-> str:
        df = self.load_master()
        try:
            tsym = df.lazy().select(
                                  ["symbol", "tradingsymbol", "expiry","instrument", "optiontype", "strikeprice"]  
                                ).filter(
                                    (pl.col("symbol") == symbol.upper())
                                    &
                                    (pl.col("instrument") == instrument)
                                    &
                                    (pl.col("expiry") == expiry)
                                    &
                                    (pl.col("optiontype") == optiontype)
                                    &
                                    (pl.col("strikeprice") == str(strikeprice))
                                ).select(
                                    "tradingsymbol"
                                ).collect().item(0, 0)
            return tsym
        except (IndexError, Exception) as e:
            logging.debug("Error Fetching TradingSymbol :: {}".format(e))
    
    def get_token(
                self,
                symbol: str= None,
                tradingsymbol: str=None,
                instrument: Literal["FUTIDX", "FUTSTK", "OPTIDX", "OPTSTK"]= "OPTIDX",
                expiry: str= None,
                optiontype: str= "XX",        
                strikeprice: Union[int, str]= 0 
                )-> str:
        df = self.load_master()
        try:
            if symbol and not tradingsymbol:
                tkn = df.lazy().select(
                                      ["token", "symbol",  "expiry", "instrument", "optiontype", "strikeprice"]  
                                    ).filter(
                                        (pl.col("symbol") == symbol.upper())
                                        &
                                        (pl.col("instrument") == instrument)
                                        &
                                        (pl.col("expiry") == expiry)
                                        &
                                        (pl.col("optiontype") == optiontype)
                                        &
                                        (pl.col("strikeprice") == str(strikeprice))
                                    ).select(
                                        "token"
                                    ).collect().item(0, 0)
                return tkn
            elif tradingsymbol:
                tkn= df.lazy().select(
                                            ["token", "tradingsymbol"]
                                        ).filter(
                                            (pl.col("tradingsymbol") == tradingsymbol.upper())
                                        ).select(
                                            "token"
                                        ).collect().item(0, 0)
                
                return tkn            
        except (IndexError, Exception) as e:
            logging.debug("Error Fetching Token :: {}".format(e))
    
    def get_strikediff(
                    self,
                    symbol: str= None,
                    )-> float:
        df = self.load_master()

        try:
            strikediff= df.lazy().select(
                                        ["symbol", "strikeprice"]
                                    ).with_columns(
                                        pl.col("strikeprice").cast(dtype= pl.Float64)
                                    ).filter(
                                        (pl.col("symbol") == symbol.upper())
                                        &
                                        (pl.col("strikeprice") > 0)
                                    ).select(
                                        "strikeprice"
                                    ).unique().sort(by="strikeprice").collect().to_series().diff(null_behavior="drop").abs().min()

            return strikediff            
        except (IndexError, Exception) as e:
            logging.debug("Error Fetching Strikediff :: {}".format(e))

