import { chakra, Text } from '@chakra-ui/react';
import ReactCountdown, { zeroPad } from 'react-countdown';
import { If, Then, Else } from 'react-if';
import { useColorValue } from '~/context';

import type { TCountdown, TRenderer } from './types';

const Renderer = (props: TRenderer): JSX.Element => {
  const { hours, minutes, seconds, completed, text } = props;
  const time = [zeroPad(seconds)];
  minutes !== 0 && time.unshift(zeroPad(minutes));
  hours !== 0 && time.unshift(zeroPad(hours));
  const bg = useColorValue('black', 'white');
  return (
    <If condition={completed}>
      <Then>
        <Text fontSize="xs" />
      </Then>
      <Else>
        <Text fontSize="xs" color="gray.500">
          {text}
          <chakra.span fontSize="xs" color={bg}>
            {time.join(':')}
          </chakra.span>
        </Text>
      </Else>
    </If>
  );
};

export const Countdown = (props: TCountdown): JSX.Element => {
  const { timeout, text } = props;
  const then = timeout * 1000;
  return (
    <ReactCountdown
      date={Date.now() + then}
      daysInHours
      renderer={renderProps => <Renderer {...renderProps} text={text} />}
    />
  );
};
