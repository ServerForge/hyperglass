import { Button, Tooltip } from '@chakra-ui/react';
import { DynamicIcon } from '~/elements';

interface PathButtonProps {
  onOpen(): void;
}

export const PathButton = (props: PathButtonProps): JSX.Element => {
  const { onOpen } = props;
  return (
    <Tooltip hasArrow label="View AS Path" placement="top">
      <Button
        mx={1}
        size="sm"
        variant="ghost"
        onClick={onOpen}
        colorScheme="secondary"
        aria-label="View AS Path"
      >
        <DynamicIcon icon={{ bi: 'BiNetworkChart' }} boxSize="16px" />
      </Button>
    </Tooltip>
  );
};
