import { Select } from '@chakra-ui/react';

import type { SelectProps } from '@chakra-ui/react';

export const PageSelect = (props: SelectProps): JSX.Element => {
  return (
    <Select size="sm" {...props}>
      {[5, 10, 20, 30, 40, 50].map(size => (
        <option key={size} value={size}>
          Show {size}
        </option>
      ))}
    </Select>
  );
};
