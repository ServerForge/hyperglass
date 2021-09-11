import type { State } from '@hookstate/core';
import type { ButtonProps } from '@chakra-ui/react';
import type { UseQueryResult } from 'react-query';
import type { Device } from '~/types';

export interface TResultHeader {
  title: string;
  loading: boolean;
  isError?: boolean;
  errorMsg: string;
  errorLevel: 'success' | 'warning' | 'error';
  runtime: number;
}

export interface TFormattedError {
  keywords: string[];
  message: string;
}

export interface TResult {
  index: number;
  device: Device;
  queryGroup: string;
  queryTarget: string;
  queryLocation: string;
  queryType: string;
}

export type TErrorLevels = 'success' | 'warning' | 'error';

export interface TCopyButton extends ButtonProps {
  copyValue: string;
}

export interface TRequeryButton extends ButtonProps {
  requery: UseQueryResult<QueryResponse>['refetch'];
}

export type TUseResults = {
  firstOpen: number | null;
  locations: { [k: string]: { complete: boolean; open: boolean; index: number } };
};

export type TUseResultsMethods = {
  toggle(loc: string): void;
  setComplete(loc: string): void;
  getOpen(): number[];
};

export type UseResultsReturn = {
  results: State<TUseResults>;
} & TUseResultsMethods;
